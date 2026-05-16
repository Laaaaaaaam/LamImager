import logging

from langchain_core.runnables import RunnableConfig

from app.core.agent.state import AgentState
from app.utils.llm_client import LLMClient
from app.tools import registry

logger = logging.getLogger(__name__)


async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
    conf = config.get("configurable", {})
    db = conf.get("db")
    provider_id = state.get("provider_id", "")
    tools = state.get("tools", [])
    raw_messages = state.get("messages", [])
    messages = []
    for m in raw_messages:
        if hasattr(m, "content"):
            d = {"role": getattr(m, "type", getattr(m, "role", "user")), "content": m.content}
            if hasattr(m, "tool_calls") and m.tool_calls:
                d["tool_calls"] = m.tool_calls
            if hasattr(m, "tool_call_id") and m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            messages.append(d)
        else:
            messages.append(m)
    max_rounds = conf.get("max_rounds", 5)
    cancel_event = conf.get("cancel_event")
    broadcaster = conf.get("broadcaster")

    from app.services.generate_service import resolve_provider_vendor
    from app.models.api_provider import ApiProvider
    from app.services.agent_service import TokenEvent, ErrorEvent
    from sqlalchemy import select

    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        if broadcaster:
            broadcaster(ErrorEvent(error="LLM provider not found"))
        return {"status": "error"}

    try:
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception as e:
        if broadcaster:
            broadcaster(ErrorEvent(error=f"API key decryption failed: {e}"))
        return {"status": "error"}

    client = LLMClient(base_url, api_key, provider.model_id)
    tool_schemas = registry.list_for_openai(tools) if tools else []

    round_idx = state.get("rounds", 0)
    forced = "required" if round_idx <= 1 else "auto"

    round_content = ""
    round_tool_calls: list[dict] = []
    tokens_in = state.get("total_tokens_in", 0)
    tokens_out = state.get("total_tokens_out", 0)

    try:
        async for event in client.chat_stream_with_tools(
            messages=messages,
            tools=tool_schemas,
            temperature=0.7,
            tool_choice=forced,
        ):
            if cancel_event and cancel_event.is_set():
                return {"status": "cancelled"}

            ev_type = event.get("type", "")
            if ev_type == "token":
                round_content += event["content"]
                if broadcaster:
                    broadcaster(TokenEvent(content=event["content"]))
            elif ev_type == "usage":
                tokens_in += event.get("tokens_in", 0)
                tokens_out += event.get("tokens_out", 0)
            elif ev_type == "tool_calls":
                round_tool_calls = event["tool_calls"]
    except Exception as e:
        logger.error(f"Agent LLM streaming failed round {round_idx}: {e}")
        if broadcaster:
            broadcaster(ErrorEvent(error=str(e)))
        return {"status": "error"}

    assistant_msg = {
        "role": "assistant",
        "content": round_content or None,
    }
    new_messages = [assistant_msg]

    if round_tool_calls:
        assistant_msg["tool_calls"] = round_tool_calls

    return {
        "messages": new_messages,
        "total_tokens_in": tokens_in,
        "total_tokens_out": tokens_out,
        "rounds": round_idx + 1,
        "status": "has_tool_calls" if round_tool_calls else "completed",
    }
