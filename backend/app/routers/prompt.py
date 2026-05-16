import json
import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.prompt import PromptOptimizeRequest, PromptOptimizeResponse
from app.services.prompt_optimizer import optimize_prompt, optimize_prompt_stream, stream_llm_chat
from app.services.agent_service import run_agent_loop, DoneEvent, ErrorEvent, CancelledEvent
from app.services.settings_service import get_use_langgraph

router = APIRouter(prefix="/api/prompt", tags=["prompt"])


class StreamRequest(BaseModel):
    messages: list[dict]
    provider_id: str
    session_id: str | None = None
    temperature: float = 0.7
    stream_type: str = "assistant"
    tools: list[str] | None = None


@router.post("/optimize", response_model=PromptOptimizeResponse)
async def api_optimize_prompt(data: PromptOptimizeRequest, db: AsyncSession = Depends(get_db)):
    result = await optimize_prompt(db, data)
    return result


@router.post("/optimize/stream")
async def api_optimize_prompt_stream(data: PromptOptimizeRequest, db: AsyncSession = Depends(get_db)):
    return StreamingResponse(
        optimize_prompt_stream(db, data),
        media_type="text/event-stream",
    )


async def _stream_with_tools_legacy(db, data: StreamRequest):
    async for event in run_agent_loop(
        db=db,
        provider_id=data.provider_id,
        messages=data.messages,
        tools=data.tools,
        session_id=data.session_id,
    ):
        if event.type == "error":
            yield f"data: {json.dumps({'error': event.error})}\n\n"
        elif event.type == "token":
            yield f"data: {json.dumps({'token': event.content})}\n\n"
        elif event.type == "tool_call":
            yield f"data: {json.dumps({'tool_call': {'name': event.name, 'args': event.args}})}\n\n"
        elif event.type == "tool_result":
            yield f"data: {json.dumps({'tool_result': {'name': event.name, 'content': event.content, 'meta': event.meta}})}\n\n"
        elif event.type == "tool_warning":
            yield f"data: {json.dumps({'tool_warning': {'name': event.name, 'reason': event.reason, 'retry_count': event.retry_count}})}\n\n"
        elif event.type == "done":
            yield f"data: {json.dumps({'done': True, 'cost': event.cost})}\n\n"


async def _stream_with_graph(db, data: StreamRequest):
    from app.core.agent.graph import build_agent_graph
    from app.services.generate_service import resolve_provider_vendor, _build_agent_context
    from app.models.api_provider import ApiProvider
    from app.services.billing_service import calc_cost, record_billing
    from sqlalchemy import select

    graph = build_agent_graph()

    events_queue: asyncio.Queue = asyncio.Queue()

    def broadcaster(event):
        events_queue.put_nowait(event)

    session_id = data.session_id
    working_messages = list(data.messages)

    if session_id:
        try:
            context = await _build_agent_context(db, session_id)
            for msg in reversed(context):
                working_messages.insert(1, msg)
        except Exception:
            pass

    initial_state = {
        "session_id": session_id or "",
        "messages": working_messages,
        "provider_id": data.provider_id,
        "tools": data.tools or [],
        "total_tokens_in": 0,
        "total_tokens_out": 0,
        "cost": 0.0,
        "rounds": 0,
        "tools_used": [],
        "status": "running",
    }

    config = {
        "configurable": {
            "db": db,
            "max_rounds": 5,
            "checkpoints": [],
            "cancel_event": None,
            "broadcaster": broadcaster,
        },
        "recursion_limit": 10,
    }

    async def _run_graph():
        try:
            result_state = await graph.ainvoke(initial_state, config)
            tokens_in = result_state.get("total_tokens_in", 0)
            tokens_out = result_state.get("total_tokens_out", 0)
            rounds = result_state.get("rounds", 1)

            result = await db.execute(select(ApiProvider).where(ApiProvider.id == data.provider_id))
            provider = result.scalar_one_or_none()
            cost = 0.0
            if provider:
                cost = calc_cost(provider, tokens_in=tokens_in, tokens_out=tokens_out, call_count=max(rounds, 1))
                try:
                    await record_billing(
                        db,
                        session_id=session_id,
                        provider_id=provider.id,
                        billing_type=provider.billing_type.value,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        cost=cost,
                        currency=provider.currency,
                        detail={"type": "assistant", "rounds": rounds, "tools_used": data.tools or []},
                    )
                except Exception as e:
                    pass

            broadcaster(DoneEvent(tokens_in=tokens_in, tokens_out=tokens_out, cost=cost))
        except Exception as e:
            broadcaster(ErrorEvent(error=str(e)))

    import asyncio as _asyncio
    task = _asyncio.create_task(_run_graph())

    try:
        while True:
            try:
                event = await asyncio.wait_for(events_queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
                break

            if event.type == "error":
                yield f"data: {json.dumps({'error': event.error})}\n\n"
                break
            elif event.type == "token":
                yield f"data: {json.dumps({'token': event.content})}\n\n"
            elif event.type == "tool_call":
                yield f"data: {json.dumps({'tool_call': {'name': event.name, 'args': event.args}})}\n\n"
            elif event.type == "tool_result":
                yield f"data: {json.dumps({'tool_result': {'name': event.name, 'content': event.content, 'meta': event.meta}})}\n\n"
            elif event.type == "tool_warning":
                yield f"data: {json.dumps({'tool_warning': {'name': event.name, 'reason': event.reason, 'retry_count': event.retry_count}})}\n\n"
            elif event.type == "done":
                yield f"data: {json.dumps({'done': True, 'cost': event.cost})}\n\n"
                break
            elif event.type == "cancelled":
                yield f"data: {json.dumps({'cancelled': True})}\n\n"
                break
    finally:
        if not task.done():
            task.cancel()


async def _stream_with_tools(db, data: StreamRequest):
    use_langgraph = await get_use_langgraph(db)
    if use_langgraph:
        async for chunk in _stream_with_graph(db, data):
            yield chunk
    else:
        async for chunk in _stream_with_tools_legacy(db, data):
            yield chunk


@router.post("/stream")
async def api_stream_chat(data: StreamRequest, db: AsyncSession = Depends(get_db)):
    if data.tools:
        return StreamingResponse(
            _stream_with_tools(db, data),
            media_type="text/event-stream",
        )
    return StreamingResponse(
        stream_llm_chat(db, data.provider_id, data.messages, data.temperature, data.session_id, data.stream_type),
        media_type="text/event-stream",
    )


@router.post("/plan")
async def api_plan_stream(data: StreamRequest, db: AsyncSession = Depends(get_db)):
    if data.tools:
        return StreamingResponse(
            _stream_with_tools(db, data),
            media_type="text/event-stream",
        )
    return StreamingResponse(
        stream_llm_chat(db, data.provider_id, data.messages, data.temperature, data.session_id, "plan"),
        media_type="text/event-stream",
    )
