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
class CancelledEvent(AgentEvent):
    type: str = "cancelled"
    partial_output: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


AGENT_SYSTEM_PROMPT = """你是 LamImager 的 AI 助手，可以调用工具来完成用户的任务。

你有以下工具可用：
- web_search: 搜索互联网获取文本信息（设计趋势、风格参考、VI规范等）
- image_search: 搜索互联网获取图片参考（风格情绪板、材质参考等）

使用方法：
1. 理解用户需求，判断是否需要搜索
2. 如果需要，调用相应的搜索工具
3. 根据搜索结果，为用户提供有用的分析和建议
4. 如果用户要求生成图片，你可以规划好方案后调用 generate_image 工具

原则：
- 主动使用搜索工具获取最新、最准确的信息
- 分析结果后用中文回答用户
- 如果是设计类问题，提供具体的视觉参考建议
- 简洁高效，不做多余解释"""


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
            ApiProvider.provider_type == ProviderType.tool,
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
                    exec_kwargs["api_key"] = tool_api_key
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
