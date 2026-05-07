from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.prompt import PromptOptimizeRequest, PromptOptimizeResponse
from app.services.prompt_optimizer import optimize_prompt, optimize_prompt_stream, stream_llm_chat

router = APIRouter(prefix="/api/prompt", tags=["prompt"])


class StreamRequest(BaseModel):
    messages: list[dict]
    provider_id: str
    session_id: str | None = None
    temperature: float = 0.7


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


@router.post("/stream")
async def api_stream_chat(data: StreamRequest, db: AsyncSession = Depends(get_db)):
    return StreamingResponse(
        stream_llm_chat(db, data.provider_id, data.messages, data.temperature, data.session_id),
        media_type="text/event-stream",
    )
