from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.prompt import PromptOptimizeRequest, PromptOptimizeResponse
from app.services.prompt_optimizer import optimize_prompt, optimize_prompt_stream, stream_llm_chat
from app.services.agent_service import run_agent_loop

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


async def _stream_with_tools(db, data: StreamRequest):
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
        elif event.type == "done":
            yield f"data: {json.dumps({'done': True, 'cost': event.cost})}\n\n"


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
