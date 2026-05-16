from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill
from app.schemas.execution import ExecutionPlan, PlanStep
from app.schemas.skill import SkillCreate, SkillImport, SkillUpdate


async def create_skill(db: AsyncSession, data: SkillCreate) -> Skill:
    skill = Skill(
        name=data.name,
        description=data.description,
        prompt_template=data.prompt_template,
        parameters=data.parameters,
        strategy=data.strategy,
        steps=data.steps,
        strategy_hint=data.strategy_hint,
        planning_bias=data.planning_bias,
        constraints=data.constraints,
        prompt_bias=data.prompt_bias,
        is_builtin=data.is_builtin,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


async def update_skill(db: AsyncSession, skill_id: str, data: SkillUpdate) -> Skill | None:
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(skill, key, value)

    await db.commit()
    await db.refresh(skill)
    return skill


async def delete_skill(db: AsyncSession, skill_id: str) -> bool:
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        return False
    await db.delete(skill)
    await db.commit()
    return True


async def get_skill(db: AsyncSession, skill_id: str) -> Skill | None:
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    return result.scalar_one_or_none()


async def list_skills(db: AsyncSession) -> list[Skill]:
    result = await db.execute(select(Skill).order_by(Skill.created_at.desc()))
    return list(result.scalars().all())


async def import_skill(db: AsyncSession, data: SkillImport) -> Skill:
    skill = Skill(
        name=data.name,
        description=data.description,
        prompt_template=data.prompt_template,
        parameters=data.parameters,
        strategy=data.strategy,
        steps=data.steps,
        strategy_hint=data.strategy_hint,
        planning_bias=data.planning_bias,
        constraints=data.constraints,
        prompt_bias=data.prompt_bias,
        is_builtin=False,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


def apply_skill(prompt: str, skill: Skill, params: dict | None = None) -> str | ExecutionPlan | dict:
    if skill.strategy_hint or skill.planning_bias or skill.constraints or skill.prompt_bias:
        return skill_to_planner_hints(skill)

    if skill.strategy and skill.steps:
        return skill_to_execution_plan(skill, prompt=prompt, params=params)

    template = skill.prompt_template
    if not template:
        return prompt

    merged_params = {**(skill.parameters or {}), **(params or {})}
    result = template.replace("{{prompt}}", prompt).replace("{prompt}", prompt)
    for key, val in merged_params.items():
        result = result.replace(f"{{{{{key}}}}}", str(val)).replace(f"{{{key}}}", str(val))
    try:
        if "{" in result and "}" in result:
            result = result.format(prompt=prompt, **merged_params)
    except (KeyError, IndexError):
        pass
    return result


def skill_to_planner_hints(skill: Skill) -> dict:
    return {
        "skill_id": skill.id,
        "skill_name": skill.name,
        "strategy_hint": skill.strategy_hint or "",
        "planning_bias": skill.planning_bias or {},
        "constraints": skill.constraints or {},
        "prompt_bias": skill.prompt_bias or {},
    }


def skill_to_execution_plan(skill: Skill, prompt: str = "", params: dict | None = None) -> ExecutionPlan:
    merged_params = {**(skill.parameters or {}), **(params or {})}
    steps_raw = skill.steps or []
    plan_steps: list[PlanStep] = []
    for i, s in enumerate(steps_raw):
        step_prompt = s.get("prompt", "")
        for key, val in merged_params.items():
            step_prompt = step_prompt.replace(f"{{{{{key}}}}}", str(val))
        step_prompt = step_prompt.replace("{{prompt}}", prompt).replace("{prompt}", prompt)
        plan_steps.append(PlanStep(
            index=i,
            prompt=step_prompt,
            negative_prompt=s.get("negative_prompt", ""),
            description=s.get("description", ""),
            image_count=s.get("image_count", 1),
            image_size=s.get("image_size", ""),
            reference_step_indices=s.get("reference_step_indices"),
            role=s.get("role", ""),
            repeat=s.get("repeat", ""),
        ))
    return ExecutionPlan(
        strategy=skill.strategy,
        steps=plan_steps,
        source="skill",
        plan_meta={"skill_id": skill.id, "skill_name": skill.name},
    )


def skill_to_response(skill: Skill) -> dict:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "prompt_template": skill.prompt_template,
        "parameters": skill.parameters or {},
        "strategy": skill.strategy or "",
        "steps": skill.steps or [],
        "strategy_hint": skill.strategy_hint or "",
        "planning_bias": skill.planning_bias or {},
        "constraints": skill.constraints or {},
        "prompt_bias": skill.prompt_bias or {},
        "is_builtin": skill.is_builtin,
        "created_at": skill.created_at,
    }
