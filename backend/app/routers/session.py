import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
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
from app.services.task_manager import TaskManager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/events")
async def session_events(request: Request):
    task_manager = TaskManager()
    last_event_id = request.headers.get("Last-Event-ID") or request.headers.get("last-event-id")
    queue_id, queue = await task_manager.subscribe(session_id=None, last_event_id=last_event_id)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'snapshot', 'data': task_manager.get_all_tasks()}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    sse_line = await asyncio.wait_for(queue.get(), timeout=30)
                    yield sse_line
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping', 'data': {}}, ensure_ascii=False)}\n\n"
        finally:
            task_manager.unsubscribe(queue_id)

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
    if data.agent_mode:
        result = await handle_agent_generate(db, data)
    else:
        result = await handle_generate(db, data)
    return result


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


@router.post("/{session_id}/agent/checkpoint")
async def api_agent_checkpoint(session_id: str, data: CheckpointRequest):
    task_manager = TaskManager()
    state = task_manager.get_checkpoint_state(session_id)
    if not state:
        return {"status": "no_checkpoint"}
    approved = data.action == "approve"
    resolved = task_manager.resolve_checkpoint(session_id, approved=approved)
    if resolved:
        event = state.get("event")
        step = event.payload.get("step") if event else None
        return {"status": data.action, "step": step}
    return {"status": "no_checkpoint"}
