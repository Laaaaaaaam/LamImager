import json
import logging

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.state import AgentState
from app.models.api_provider import ApiProvider, ProviderType
from app.services.billing_service import calc_cost, record_billing
from app.services.agent_service import ToolCallEvent, ToolResultEvent, WarningEvent
from app.tools import registry

logger = logging.getLogger(__name__)


def _parse_fn_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _truncate_tool_result(content: str, tool_name: str, max_len: int = 800) -> str:
    if len(content) <= max_len:
        return content
    if tool_name in ("web_search", "image_search"):
        lines = content.split("\n")
        kept = lines[:3]
        return "\n".join(kept) + f"\n... (truncated, {len(lines)} results total)"
    return content[:max_len] + "..."


async def tools_node(state: AgentState, config: RunnableConfig) -> dict:
    conf = config.get("configurable", {})
    db: AsyncSession = conf.get("db")
    session_id = state.get("session_id")
    tools = state.get("tools", [])
    checkpoints = conf.get("checkpoints", [])
    cancel_event = conf.get("cancel_event")
    broadcaster = conf.get("broadcaster")

    messages = state.get("messages", [])
    dict_messages = []
    for m in messages:
        if hasattr(m, "content"):
            d = {"role": getattr(m, "type", getattr(m, "role", "user")), "content": m.content}
            if hasattr(m, "tool_calls") and m.tool_calls:
                d["tool_calls"] = m.tool_calls
            if hasattr(m, "tool_call_id") and m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            dict_messages.append(d)
        else:
            dict_messages.append(m)
    last_assistant = None
    for msg in reversed(dict_messages):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            last_assistant = msg
            break

    if not last_assistant:
        return {"status": "completed"}

    tool_calls = last_assistant.get("tool_calls", [])

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
            from app.services.generate_service import resolve_provider_vendor
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

    tool_messages = []
    tools_used = list(state.get("tools_used", []))

    for tc in tool_calls:
        fn = tc.get("function", {})
        fn_name = fn.get("name", "")
        fn_args = _parse_fn_args(fn.get("arguments", {}))

        if broadcaster:
            broadcaster(ToolCallEvent(name=fn_name, args=fn_args))

        if fn_name in checkpoints:
            if broadcaster:
                broadcaster(WarningEvent(name=fn_name, reason=f"Checkpoint '{fn_name}' not configured in graph mode", retry_count=0))

        if cancel_event and cancel_event.is_set():
            return {"status": "cancelled"}

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
                    except Exception:
                        pass

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
        if broadcaster:
            broadcaster(ToolResultEvent(name=fn_name, content=truncated, meta=result_meta))

        tool_messages.append({
            "role": "tool",
            "tool_call_id": tc.get("id", ""),
            "content": truncated,
        })
        if fn_name not in tools_used:
            tools_used.append(fn_name)

    return {
        "messages": tool_messages,
        "tools_used": tools_used,
        "status": "tool_calls_done",
    }
