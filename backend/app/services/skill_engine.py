from __future__ import annotations
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill
from app.schemas.skill import SkillCreate, SkillImport, SkillUpdate


async def create_skill(db: AsyncSession, data: SkillCreate) -> Skill:
    skill = Skill(
        name=data.name,
        description=data.description,
        prompt_template=data.prompt_template,
        parameters=data.parameters,
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
        is_builtin=False,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


def apply_skill(prompt: str, skill: Skill, params: dict = None) -> str:
    template = skill.prompt_template
    if not template:
        return prompt

    merged_params = {**(skill.parameters or {}), **(params or {})}
    try:
        return template.format(prompt=prompt, **merged_params)
    except (KeyError, IndexError):
        return template.replace("{{prompt}}", prompt).replace("{prompt}", prompt)


def skill_to_response(skill: Skill) -> dict:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "prompt_template": skill.prompt_template,
        "parameters": skill.parameters or {},
        "is_builtin": skill.is_builtin,
        "created_at": skill.created_at,
    }
