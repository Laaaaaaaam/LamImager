from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_provider import ApiProvider, ProviderType
from app.services.billing_service import calc_cost, record_billing
from app.tools import registry
from app.services.api_manager import resolve_provider_vendor
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


AGENT_SYSTEM_PROMPT = """你是 LamImager 的图像生成 Agent。你的核心职责是调用工具生成图片，而非提供建议。

**强制规则**:
1. 用户要求生成图片时，必须调用工具执行，禁止仅回复文字描述或建议
2. 信息不足时，优先做出合理假设继续执行；仅当关键信息（如数量、主题）完全缺失时才简短追问一次
3. 用户可能提供参考图片，标记为 [图N] 格式，你应在生成时基于这些视觉参考

## 可用工具

- **generate_image**: 生成图片。参数：prompt(英文生图提示词)、count(生成数量1-4，仅用于同一 prompt 的随机变体)、reference_urls(参考图URL，可选)。

- **plan**: 管理和使用生图模板。action=list 列出模板，action=apply 应用模板，action=create 保存新模板。

- **image_search**: 搜索互联网图片作为视觉参考。

- **web_search**: 搜索互联网文本信息。

## Plan 策略

| 策略 | 适用场景 |
|------|---------|
| parallel(并发) | 批量独立图、变体探索，各图独立生成 |
| iterative(顺序) | 分步骤任务，按顺序依次执行每个步骤 |
| radiate(辐射) | 套图/表情包/图标集，先生成风格锚点图再扩展，风格高度统一 |

## 工作规则（路径选择）

**直接生成**（generate_image）：
- 单张图请求
- 少量独立图（2-4张），彼此无风格关联（如"画3张不同风格的猫"）
- 若每张图的内容或风格不同，使用多次 generate_image(count=1)，每次给出不同 prompt
- count 参数仅用于"同一 prompt 的 N 个随机变体"，不用于不同内容的任务
- 多内容任务（如三视图、多角色、多表情）由服务端自动解析，你必须为每个独立视角/角色/表情生成一张图
- **禁止**将多个视角合并为一张 sheet/turnaround，除非用户明确要求"一张图里排版"或"设定表"

**计划生成**（必须走 plan）：
- 风格统一的多图：套图、表情包、图标集、系列插画
- 有先后依赖的任务：先草图再精修、先Logo再延伸物料
- 关键词识别：套/组/系列/一套/表情包/图标集/统一风格
- 流程：plan(action="list") → 找到合适模板则 plan(action="apply")，否则 plan(action="create") → plan(action="apply")
- 对于 radiate/套图模板，apply 时必须提供 variables={items:[{"prompt":"..."}, ...], style:"...", overall_theme:"..."}
- apply 成功后必须继续执行：根据返回的 steps，逐步调用 generate_image 完成每一步，禁止仅回复"已生成N个步骤"而不实际生图

**搜索辅助**（可选，不阻塞主流程）：
- 用户提到"参考/搜索/流行/趋势"时先搜索再生成
- image_search 结果可作为 generate_image 的 reference_urls"""


def _parse_fn_args(raw_args) -> dict:
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
    if isinstance(raw_args, dict):
        return raw_args
    return {}


def _truncate_tool_result(content: str, tool_name: str, max_chars: int = 800) -> str:
    if len(content) <= max_chars:
        return content
    suffix = "\n... [truncated]"
    if tool_name == "web_search":
        items = content.split("\n\n")
        if len(items) > 3:
            head = "\n\n".join(items[:3])
            tail = f"\n\n... 其余 {len(items) - 3} 条结果已省略"
            combined = head + tail
            if len(combined) > max_chars:
                return combined[:max_chars - len(suffix)] + suffix
            return combined
    if len(content) > max_chars:
        return content[:max_chars - len(suffix)] + suffix
    return content


def _estimate_tokens(msgs: list[dict]) -> int:
    total = 0
    for m in msgs:
        s = m.get("content", "") or ""
        if isinstance(s, list):
            for part in s:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += len(part.get("text", ""))
        else:
            total += len(s)
    return total // 3


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
    on_checkpoint: Callable[[str, dict], asyncio.Future] | None = None,
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
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception as e:
        yield ErrorEvent(error=f"API key decryption failed: {e}")
        return

    client = LLMClient(base_url, api_key, provider.model_id)
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
            _, tool_api_key = await resolve_provider_vendor(db, tool_provider)
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

    image_size = "1024x1024"
    try:
        from app.services.settings_service import get_setting
        setting = await get_setting(db, "default_image_size")
        if setting and isinstance(setting, dict):
            image_size = str(setting.get("value", "1024x1024"))
    except Exception:
        pass

    total_tokens_in = 0
    total_tokens_out = 0
    working_messages = list(messages)
    partial_output = ""

    MAX_WORKING_TOKENS = 6000

    round_idx = -1
    for round_idx in range(max_rounds):
        if cancel_event and cancel_event.is_set():
            await _record_partial_billing(db, session_id, provider, total_tokens_in, total_tokens_out, round_idx, tools)
            yield CancelledEvent(partial_output=partial_output, tokens_in=total_tokens_in, tokens_out=total_tokens_out)
            return

        if _estimate_tokens(working_messages) > MAX_WORKING_TOKENS:
            system_msg = working_messages[0]
            recent = working_messages[-8:]
            kept = [system_msg]
            for msg in working_messages[1:-8]:
                if msg.get("tool_call_id") or msg.get("role") == "tool":
                    continue
            for msg in recent:
                if msg.get("role") == "tool":
                    tool_call_id = msg.get("tool_call_id")
                    if tool_call_id:
                        has_call = any(
                            m.get("role") == "assistant" and
                            any(tc.get("id") == tool_call_id for tc in (m.get("tool_calls") or []))
                            for m in kept + recent
                        )
                        if not has_call:
                            continue
                kept.append(msg)
            working_messages = kept
            logger.info(f"Agent working_messages capped: {_estimate_tokens(working_messages)} tokens after truncation")

        round_content = ""
        round_tool_calls: list[dict] = []

        try:
            forced = "required" if round_idx <= 1 else "auto"
            async for event in client.chat_stream_with_tools(
                messages=working_messages,
                tools=tool_schemas,
                temperature=0.7,
                tool_choice=forced,
            ):
                if cancel_event and cancel_event.is_set():
                    await _record_partial_billing(db, session_id, provider, total_tokens_in, total_tokens_out, round_idx + 1, tools)
                    yield CancelledEvent(partial_output=partial_output, tokens_in=total_tokens_in, tokens_out=total_tokens_out)
                    return

                ev_type = event.get("type", "")
                if ev_type == "token":
                    round_content += event["content"]
                    partial_output += event["content"]
                    yield TokenEvent(content=event["content"])
                elif ev_type == "usage":
                    total_tokens_in += event.get("tokens_in", 0)
                    total_tokens_out += event.get("tokens_out", 0)
                elif ev_type == "tool_calls":
                    round_tool_calls = event["tool_calls"]
        except Exception as e:
            logger.error(f"Agent LLM streaming failed round {round_idx}: {e}")
            yield ErrorEvent(error=str(e))
            return

        if not round_tool_calls:
            break

        assistant_msg: dict = {
            "role": "assistant",
            "content": round_content or None,
            "tool_calls": round_tool_calls,
        }
        working_messages.append(assistant_msg)

        for tc in round_tool_calls:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            fn_args = _parse_fn_args(fn.get("arguments", {}))

            yield ToolCallEvent(name=fn_name, args=fn_args)

            if fn_name in checkpoints:
                if on_checkpoint:
                    try:
                        approved = await on_checkpoint(fn_name, fn_args)
                        if not approved:
                            await _record_partial_billing(db, session_id, provider, total_tokens_in, total_tokens_out, round_idx + 1, tools)
                            yield CancelledEvent(partial_output=partial_output, tokens_in=total_tokens_in, tokens_out=total_tokens_out)
                            return
                    except Exception as e:
                        logger.warning(f"Checkpoint callback failed: {e}")
                else:
                    yield WarningEvent(name=fn_name, reason=f"Checkpoint '{fn_name}' not configured", retry_count=0)

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
                    exec_kwargs["image_provider_id"] = image_provider.id if image_provider else ""
                    exec_kwargs["image_size"] = image_size
                    exec_kwargs["session_id"] = session_id

                    # Auto-inject context references for generate_image
                    if fn_name == "generate_image" and not exec_kwargs.get("reference_urls"):
                        try:
                            from app.services.agent_intent_service import resolve_context_references
                            refs = await resolve_context_references(
                                db=db,
                                session_id=session_id,
                                prompt="",
                                context_messages=[],
                                reference_labels=[],
                            )
                            if refs:
                                exec_kwargs["reference_urls"] = refs[:4]
                                logger.debug(f"Injected {len(refs[:4])} context references into generate_image")
                        except Exception as e:
                            logger.debug(f"Could not resolve context references: {e}")

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

            truncated = _truncate_tool_result(result_content, fn_name)
            yield ToolResultEvent(name=fn_name, content=truncated, meta=result_meta)

            tool_msg = {
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": truncated,
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
