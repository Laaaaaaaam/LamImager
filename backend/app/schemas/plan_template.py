from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TemplateVariableSchema(BaseModel):
    key: str
    type: str = "string"
    label: str = ""
    default: str = ""
    options: list[str] | None = None
    required: bool = False


class PlanStepConditionSchema(BaseModel):
    type: str = "none"
    on_pass: dict = {}
    on_fail: dict = {}


class PlanStepSchema(BaseModel):
    prompt: str
    negative_prompt: str = ""
    description: str = ""
    image_count: int = 1
    image_size: str = ""
    role: str = ""
    repeat: str = ""
    reference_step_indices: list[int] | None = None
    checkpoint: dict | None = None
    condition: PlanStepConditionSchema | None = None


class PlanTemplateCreate(BaseModel):
    name: str
    description: str = ""
    strategy: str = "parallel"
    steps: list[PlanStepSchema] = []
    variables: list[TemplateVariableSchema] = []


class PlanTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    strategy: str | None = None
    steps: list[PlanStepSchema] | None = None
    variables: list[TemplateVariableSchema] | None = None


class PlanTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    strategy: str
    steps: list[dict]
    variables: list[dict]
    is_builtin: bool
    created_at: datetime
    updated_at: datetime


class PlanTemplateApplyRequest(BaseModel):
    variables: dict[str, str] = {}
