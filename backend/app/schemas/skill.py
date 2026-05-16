from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    prompt_template: str = ""
    parameters: dict = {}
    is_builtin: bool = False
    strategy: str = ""
    steps: list[dict] = []
    strategy_hint: str = ""
    planning_bias: dict = {}
    constraints: dict = {}
    prompt_bias: dict = {}


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    parameters: dict | None = None
    strategy: str | None = None
    steps: list[dict] | None = None
    strategy_hint: str | None = None
    planning_bias: dict | None = None
    constraints: dict | None = None
    prompt_bias: dict | None = None


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    prompt_template: str
    parameters: dict
    is_builtin: bool
    strategy: str
    steps: list[dict]
    strategy_hint: str
    planning_bias: dict
    constraints: dict
    prompt_bias: dict
    created_at: datetime


class SkillImport(BaseModel):
    name: str
    description: str = ""
    prompt_template: str = ""
    parameters: dict = {}
    strategy: str = ""
    steps: list[dict] = []
    strategy_hint: str = ""
    planning_bias: dict = {}
    constraints: dict = {}
    prompt_bias: dict = {}
