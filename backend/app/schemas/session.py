from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    title: str = "新会话"


class SessionUpdate(BaseModel):
    title: str | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    status: str = "idle"
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    cost: float = 0
    tokens: int = 0


class MessageCreate(BaseModel):
    content: str
    message_type: str = "text"
    metadata: dict = {}


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: str
    content: str
    message_type: str
    metadata: dict
    created_at: datetime


class GenerateRequest(BaseModel):
    session_id: str | None = None
    prompt: str
    negative_prompt: str = ""
    image_count: int = Field(1, ge=1, le=16)
    image_size: str = "1024x1024"
    skill_ids: list[str] = []
    optimize_directions: list[str] = []
    custom_optimize_instruction: str = ""
    reference_images: list[str] = []
    reference_labels: list[dict] = []
    context_messages: list[dict] = []
    plan_strategy: str = ""
    agent_mode: bool = False
    agent_tools: list[str] = []
    agent_plan_strategy: str = ""
    refine_mode: bool = False
    selected_image_url: str = ""


class ExecutePlanStep(BaseModel):
    prompt: str
    negative_prompt: str = ""
    description: str = ""
    image_count: int = 1
    image_size: str = ""
    reference_step_indices: list[int] | None = None
    metadata: dict = {}


class ExecutePlanRequest(BaseModel):
    strategy: str = "parallel"
    steps: list[ExecutePlanStep] = []
    reference_images: list[str] = []
    reference_labels: list[dict] = []
    context_messages: list[dict] = []
    negative_prompt: str = ""
    image_size: str = "1024x1024"
