import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.session import (
    ExecutePlanRequest,
    GenerateRequest,
    MessageCreate,
    MessageResponse,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
)
from app.services.session_manager import (
    add_message,
    create_session,
    delete_session,
    get_messages,
    get_session_detail,
    list_sessions,
    message_to_response,
    update_session,
)
from app.services.generate_service import handle_generate, handle_agent_generate, handle_execute_plan
from app.services.task_manager import TaskManager, TaskStatus

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/events")
async def session_events(request: Request, session_id: str | None = None):
    task_manager = TaskManager()
    last_event_id = request.headers.get("Last-Event-ID") or request.headers.get("last-event-id")
    queue_id, queue = await task_manager.subscribe(session_id=session_id, last_event_id=last_event_id)
    logger = logging.getLogger(__name__)
    logger.info(f"SSE connected: qid={queue_id} session={session_id} registry_size={len(task_manager._queue_registry)}")

    async def event_generator():
        count = 0
        try:
            yield f"data: {json.dumps({'type': 'snapshot', 'data': task_manager.get_all_tasks()}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    sse_line = await asyncio.wait_for(queue.get(), timeout=30)
                    count += 1
                    if "checkpoint" in sse_line:
                        logger.info(f"SSE: checkpoint event delivered (#{count})")
                    yield sse_line
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping', 'data': {}}, ensure_ascii=False)}\n\n"
        finally:
            task_manager.unsubscribe(queue_id)
            logger.info(f"SSE disconnected: qid={queue_id} events_sent={count}")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("")
async def api_create_session(data: SessionCreate = SessionCreate(), db: AsyncSession = Depends(get_db)):
    session = await create_session(db, data)
    detail = await get_session_detail(db, session.id)
    return detail


@router.get("")
async def api_list_sessions(db: AsyncSession = Depends(get_db)):
    return await list_sessions(db)


@router.get("/{session_id}")
async def api_get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    detail = await get_session_detail(db, session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@router.put("/{session_id}")
async def api_update_session(session_id: str, data: SessionUpdate, db: AsyncSession = Depends(get_db)):
    session = await update_session(db, session_id, data)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    detail = await get_session_detail(db, session_id)
    return detail


@router.delete("/{session_id}")
async def api_delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    success = await delete_session(db, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def api_get_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    messages = await get_messages(db, session_id)
    return [message_to_response(m) for m in messages]


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def api_add_message(session_id: str, data: MessageCreate, db: AsyncSession = Depends(get_db)):
    message = await add_message(db, session_id, data)
    return message_to_response(message)


@router.post("/{session_id}/generate")
async def api_generate(session_id: str, data: GenerateRequest, db: AsyncSession = Depends(get_db)):
    data.session_id = session_id
    try:
        if data.agent_mode:
            asyncio.create_task(_run_agent_background(session_id, data))
            return {"status": "started", "session_id": session_id}
        else:
            result = await handle_generate(db, data)
            return result
    except Exception as e:
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"api_generate error: {e}\n{traceback.format_exc()}")
        return Response(
            content=json.dumps({"error": str(e), "detail": traceback.format_exc()}, ensure_ascii=False),
            status_code=500,
            media_type="application/json",
        )


async def _run_agent_background(session_id: str, data: GenerateRequest):
    from app.database import async_session
    from app.services.task_manager import task_manager
    from app.core.events import LamEvent
    async with async_session() as bg_db:
        try:
            await handle_agent_generate(bg_db, data)
        except Exception as e:
            import traceback
            logging.getLogger(__name__).error(f"_run_agent_background error: {e}\n{traceback.format_exc()}")
            task_manager.update_task(session_id, TaskStatus.IDLE)
            await task_manager.publish(LamEvent(
                event_type="task_failed",
                correlation_id=f"agent-{session_id}",
                payload={"type": "agent_error", "session_id": session_id, "error": str(e)},
            ))


@router.post("/{session_id}/execute-plan")
async def api_execute_plan(session_id: str, data: ExecutePlanRequest, db: AsyncSession = Depends(get_db)):
    return await handle_execute_plan(db, session_id, data)


@router.post("/{session_id}/cancel")
async def api_cancel(session_id: str):
    task_manager = TaskManager()
    task_manager.cancel_task(session_id)
    return {"message": "Cancelled"}


class CheckpointRequest(BaseModel):
    action: str = "approve"
    feedback: str = ""
    retry_level: str = "approve"


@router.post("/{session_id}/agent/checkpoint")
async def api_agent_checkpoint(session_id: str, data: CheckpointRequest):
    task_manager = TaskManager()
    logger = __import__("logging").getLogger(__name__)
    logger.info(f"checkpoint API called: session={session_id} action={data.action}")
    state = task_manager.get_checkpoint_state(session_id)
    if not state:
        return {"status": "no_checkpoint"}

    action = data.action
    retry_level = data.retry_level
    if action == "retry_step":
        retry_level = "retry_step"
    elif action == "replan":
        retry_level = "replan"
    elif action == "approve":
        retry_level = "approve"

    resolved = task_manager.resolve_checkpoint(session_id, approved=(retry_level == "approve"), retry_level=retry_level)
    if resolved:
        step_info = state.get("event", {}).get("payload", {}).get("step") if isinstance(state.get("event"), dict) or hasattr(state.get("event"), "payload") else None
        return {"status": "resolved", "retry_level": retry_level, "step": step_info}
    return {"status": "no_checkpoint"}
