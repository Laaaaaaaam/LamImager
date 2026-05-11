
from app.core.events import LamEvent
from app.services.agent_service import (
    AgentEvent,
    CancelledEvent,
    DoneEvent,
    ErrorEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    WarningEvent,
)


def agent_event_to_lam_event(
    agent_evt: AgentEvent,
    session_id: str,
    correlation_id: str,
) -> LamEvent:
    if isinstance(agent_evt, TokenEvent):
        return LamEvent(
            event_type="task_progress",
            correlation_id=correlation_id,
            payload={
                "type": "agent_token",
                "session_id": session_id,
                "content": agent_evt.content,
            },
        )
    if isinstance(agent_evt, ToolCallEvent):
        return LamEvent(
            event_type="task_progress",
            correlation_id=correlation_id,
            payload={
                "type": "agent_tool_call",
                "session_id": session_id,
                "name": agent_evt.name,
                "args": agent_evt.args or {},
            },
        )
    if isinstance(agent_evt, ToolResultEvent):
        return LamEvent(
            event_type="task_progress",
            correlation_id=correlation_id,
            payload={
                "type": "agent_tool_result",
                "session_id": session_id,
                "name": agent_evt.name,
                "content": agent_evt.content,
                "meta": agent_evt.meta or {},
            },
        )
    if isinstance(agent_evt, WarningEvent):
        return LamEvent(
            event_type="task_progress",
            correlation_id=correlation_id,
            payload={
                "type": "agent_tool_warning",
                "session_id": session_id,
                "name": agent_evt.name,
                "reason": agent_evt.reason,
                "retry_count": agent_evt.retry_count,
            },
        )
    if isinstance(agent_evt, DoneEvent):
        return LamEvent(
            event_type="task_completed",
            correlation_id=correlation_id,
            payload={
                "type": "agent_done",
                "session_id": session_id,
                "tokens_in": agent_evt.tokens_in,
                "tokens_out": agent_evt.tokens_out,
                "cost": agent_evt.cost,
            },
        )
    if isinstance(agent_evt, ErrorEvent):
        return LamEvent(
            event_type="task_failed",
            correlation_id=correlation_id,
            payload={
                "type": "agent_error",
                "session_id": session_id,
                "error": agent_evt.error,
            },
        )
    if isinstance(agent_evt, CancelledEvent):
        return LamEvent(
            event_type="task_completed",
            correlation_id=correlation_id,
            payload={
                "type": "agent_cancelled",
                "session_id": session_id,
                "partial_output": agent_evt.partial_output,
                "tokens_in": agent_evt.tokens_in,
                "tokens_out": agent_evt.tokens_out,
            },
        )
    return LamEvent(
        event_type="task_progress",
        correlation_id=correlation_id,
        payload={
            "type": "agent_unknown",
            "session_id": session_id,
        },
    )
