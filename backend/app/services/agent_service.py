from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_provider import ApiProvider, ProviderType
from app.services.billing_service import calc_cost, record_billing
from app.tools import registry
from app.utils.crypto import decrypt
from app.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    type: str


@dataclass
class TokenEvent(AgentEvent):
    type: str = "token"
    content: str = ""


@dataclass
class ToolCallEvent(AgentEvent):
    type: str = "tool_call"
    name: str = ""
    args: dict | None = None


@dataclass
class ToolResultEvent(AgentEvent):
    type: str = "tool_result"
    name: str = ""
    content: str = ""
    meta: dict | None = None


@dataclass
class DoneEvent(AgentEvent):
    type: str = "done"
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0


@dataclass
class ErrorEvent(AgentEvent):
    type: str = "error"
    error: str = ""


@dataclass
class WarningEvent(AgentEvent):
    type: str = "tool_warning"
    name: str = ""
    reason: str = ""
    retry_count: int = 0


@dataclass
class CancelledEvent(AgentEvent):
    type: str = "cancelled"
    partial_output: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


AGENT_SYSTEM_PROMPT = """你是 LamImager 的 AI 助手，可以帮助用户搜索参考、生成计划、并创建图片。

## 可用工具

- **generate_image**: 生成图片。参数：prompt(英文生图提示词)、count(生成数量，默认1)、reference_urls(参考图URL，可选)。**仅用于生成单张/少量独立图片。**

- **plan**: 管理和使用生图模板。**当需要生成多张风格统一的套图时，必须先调用 plan**。action=list 列出模板，action=apply 应用模板（含「套图生成」模板自动锚定风格）。

- **image_search**: 搜索互联网图片作为视觉参考。

- **web_search**: 搜索互联网文本信息。

## 规则

1. **单张/独立图** → 直接调用 generate_image(prompt, count=1)
2. **多张风格统一图/套图** → 先调用 plan(action="list")，看到「套图生成」模板 → plan(action="apply", template_id=..., variables={items: [...], style: "..."})
3. 搜索可选用，不阻塞流程

请用中文回复用户。"""


def _parse_fn_args(raw_args) -> dict:
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
    if isinstance(raw_args, dict):
        return raw_args
    return {}


async def _record_partial_billing(db, session_id, provider, tokens_in, tokens_out, rounds, tools):
    try:
        cost = calc_cost(provider, tokens_in=tokens_in, tokens_out=tokens_out, call_count=max(rounds, 1))
        await record_billing(
            db,
            session_id=session_id,
            provider_id=provider.id,
            billing_type=provider.billing_type.value,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            currency=provider.currency,
            detail={"type": "assistant", "rounds": rounds, "tools_used": tools, "cancelled": True},
        )
    except Exception as e:
        logger.warning(f"Partial billing record failed: {e}")


async def run_agent_loop(
    db: AsyncSession,
    provider_id: str,
    messages: list[dict],
    tools: list[str],
    session_id: str | None = None,
    max_rounds: int = 5,
    checkpoints: list[str] | None = None,
    cancel_event: asyncio.Event | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    checkpoints = checkpoints or []

    result = await db.execute(
        select(ApiProvider).where(ApiProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        yield ErrorEvent(error="LLM provider not found")
        return

    try:
        api_key = decrypt(provider.api_key_enc)
    except Exception as e:
        yield ErrorEvent(error=f"API key decryption failed: {e}")
        return

    client = LLMClient(provider.base_url, api_key, provider.model_id)
    tool_schemas = registry.list_for_openai(tools)

    tool_provider_result = await db.execute(
        select(ApiProvider).where(
            ApiProvider.provider_type == ProviderType.web_search,
            ApiProvider.is_active == True,
        )
    )
    tool_provider = tool_provider_result.scalars().first()
    tool_api_key = ""
    if tool_provider:
        try:
            tool_api_key = decrypt(tool_provider.api_key_enc)
        except Exception as e:
            logger.warning(f"Tool api key decryption failed: {e}")

    search_retry_count = 3
    try:
        from app.services.settings_service import get_setting
        setting = await get_setting(db, "search_retry_count")
        if setting and isinstance(setting, dict):
            search_retry_count = int(setting.get("value", 3))
    except Exception:
        pass

    image_provider_result = await db.execute(
        select(ApiProvider).where(
            ApiProvider.provider_type == ProviderType.image_gen,
            ApiProvider.is_active == True,
        )
    )
    image_provider = image_provider_result.scalars().first()
    image_api_key = ""
    image_base_url = ""
    image_model_id = ""
    if image_provider:
        try:
            image_api_key = decrypt(image_provider.api_key_enc)
            image_base_url = image_provider.base_url
            image_model_id = image_provider.model_id
        except Exception as e:
            logger.warning(f"Image api key decryption failed: {e}")

    total_tokens_in = 0
    total_tokens_out = 0
    working_messages = list(messages)
    partial_output = ""

    for round_idx in range(max_rounds):
        if cancel_event and cancel_event.is_set():
            await _record_partial_billing(db, session_id, provider, total_tokens_in, total_tokens_out, round_idx, tools)
            yield CancelledEvent(partial_output=partial_output, tokens_in=total_tokens_in, tokens_out=total_tokens_out)
            return

        try:
            response = await client.chat(
                messages=working_messages,
                temperature=0.7,
                tools=tool_schemas,
            )
        except Exception as e:
            logger.error(f"Agent LLM call failed round {round_idx}: {e}")
            yield ErrorEvent(error=str(e))
            return

        usage = response.get("usage", {})
        round_tokens_in = usage.get("prompt_tokens", 0)
        round_tokens_out = usage.get("completion_tokens", 0)
        total_tokens_in += round_tokens_in
        total_tokens_out += round_tokens_out

        content = LLMClient.extract_content(response)
        tool_calls = LLMClient.extract_tool_calls(response)

        if content:
            partial_output += content
            yield TokenEvent(content=content)

        if not tool_calls:
            break

        assistant_msg: dict = {
            "role": "assistant",
            "content": content or None,
            "tool_calls": tool_calls,
        }
        working_messages.append(assistant_msg)

        for tc in tool_calls:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            fn_args = _parse_fn_args(fn.get("arguments", {}))

            yield ToolCallEvent(name=fn_name, args=fn_args)

            if fn_name in checkpoints:
                yield ErrorEvent(error=f"Checkpoint '{fn_name}' requires user approval (not yet implemented)")
                break

            if cancel_event and cancel_event.is_set():
                await _record_partial_billing(db, session_id, provider, total_tokens_in, total_tokens_out, round_idx + 1, tools)
                yield CancelledEvent(partial_output=partial_output, tokens_in=total_tokens_in, tokens_out=total_tokens_out)
                return

            tool = registry.get(fn_name)
            if not tool:
                result_content = f"未找到工具: {fn_name}"
                result_meta = {"error": "tool_not_found"}
            else:
                try:
                    exec_kwargs = dict(fn_args)
                    exec_kwargs["db"] = db
                    exec_kwargs["api_key"] = tool_api_key
                    exec_kwargs["retry_count"] = search_retry_count
                    exec_kwargs["image_api_key"] = image_api_key
                    exec_kwargs["image_base_url"] = image_base_url
                    exec_kwargs["image_model_id"] = image_model_id
                    tool_result = await tool.execute(**exec_kwargs)
                    result_content = tool_result.content
                    result_meta = tool_result.meta

                    if tool_provider:
                        try:
                            tool_cost = calc_cost(tool_provider, call_count=1)
                            query_text = str(exec_kwargs.get("query", ""))
                            await record_billing(
                                db,
                                session_id=session_id,
                                provider_id=tool_provider.id,
                                billing_type=tool_provider.billing_type.value,
                                tokens_in=len(query_text),
                                tokens_out=len(result_content),
                                cost=tool_cost,
                                currency=tool_provider.currency,
                                detail={"type": "tool", "tool_name": fn_name, "query": query_text[:100]},
                            )
                        except Exception as be:
                            logger.warning(f"Tool billing failed: {be}")
                except Exception as e:
                    logger.error(f"Tool {fn_name} execution failed: {e}")
                    result_content = f"工具 {fn_name} 执行失败: {e}"
                    result_meta = {"error": str(e)}

            yield ToolResultEvent(name=fn_name, content=result_content, meta=result_meta)

            tool_msg = {
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": result_content,
            }
            working_messages.append(tool_msg)

    cost = calc_cost(provider, tokens_in=total_tokens_in, tokens_out=total_tokens_out, call_count=max(round_idx + 1, 1))

    try:
        await record_billing(
            db,
            session_id=session_id,
            provider_id=provider.id,
            billing_type=provider.billing_type.value,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            cost=cost,
            currency=provider.currency,
            detail={"type": "assistant", "rounds": round_idx + 1, "tools_used": tools},
        )
    except Exception as e:
        logger.error(f"Agent billing record failed: {e}")

    yield DoneEvent(tokens_in=total_tokens_in, tokens_out=total_tokens_out, cost=cost)
