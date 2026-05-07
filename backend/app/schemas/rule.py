from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.rule import RuleType


class RuleCreate(BaseModel):
    name: str
    rule_type: RuleType
    config: dict = {}
    is_active: bool = True
    priority: int = 0


class RuleUpdate(BaseModel):
    name: str | None = None
    rule_type: RuleType | None = None
    config: dict | None = None
    is_active: bool | None = None
    priority: int | None = None


class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    rule_type: str
    config: dict
    is_active: bool
    priority: int
    created_at: datetime
