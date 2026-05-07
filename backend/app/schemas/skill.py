from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    prompt_template: str = ""
    parameters: dict = {}
    is_builtin: bool = False


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    parameters: dict | None = None


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    prompt_template: str
    parameters: dict
    is_builtin: bool
    created_at: datetime


class SkillImport(BaseModel):
    name: str
    description: str = ""
    prompt_template: str = ""
    parameters: dict = {}
