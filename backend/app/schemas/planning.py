from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class PlanningContext(BaseModel):
    session_id: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    image_count: int = 1
    image_size: str = "1024x1024"
    reference_images: list[str] = []
    reference_labels: list[dict] = []
    context_messages: list[dict] = []
    skill_ids: list[str] = []
    optimize_directions: list[str] = []
    custom_optimize_instruction: str = ""
    agent_mode: bool = False
    agent_tools: list[str] = []
    agent_plan_strategy: str = ""
    image_provider_id: str | None = None
    llm_provider_id: str | None = None
    search_context: str = ""
    context_images: list[str] | None = None

    @classmethod
    def from_generate_request(
        cls,
        data: "GenerateRequest",
        image_provider_id: str | None = None,
        llm_provider_id: str | None = None,
        search_context: str = "",
        context_images: list[str] | None = None,
    ) -> PlanningContext:
        return cls(
            session_id=data.session_id or "",
            prompt=data.prompt,
            negative_prompt=data.negative_prompt,
            image_count=data.image_count,
            image_size=data.image_size,
            reference_images=data.reference_images,
            reference_labels=data.reference_labels,
            context_messages=data.context_messages,
            skill_ids=data.skill_ids,
            optimize_directions=data.optimize_directions,
            custom_optimize_instruction=data.custom_optimize_instruction,
            agent_mode=data.agent_mode,
            agent_tools=data.agent_tools,
            agent_plan_strategy=data.agent_plan_strategy,
            image_provider_id=image_provider_id,
            llm_provider_id=llm_provider_id,
            search_context=search_context,
            context_images=context_images,
        )


@runtime_checkable
class SkillInterface(Protocol):
    name: str
    description: str
    prompt_template: str
    parameters: dict
    strategy: str
    steps: list[dict]
