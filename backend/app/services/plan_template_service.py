from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan_template import PlanTemplate
from app.schemas.plan_template import (
    PlanTemplateCreate,
    PlanTemplateUpdate,
    PlanTemplateApplyRequest,
)


async def list_templates(db: AsyncSession) -> list[PlanTemplate]:
    result = await db.execute(select(PlanTemplate).order_by(PlanTemplate.is_builtin.desc(), PlanTemplate.name.asc()))
    return list(result.scalars().all())


async def get_template(db: AsyncSession, template_id: str) -> PlanTemplate | None:
    result = await db.execute(select(PlanTemplate).where(PlanTemplate.id == template_id))
    return result.scalar_one_or_none()


async def create_template(db: AsyncSession, data: PlanTemplateCreate) -> PlanTemplate:
    template = PlanTemplate(
        name=data.name,
        description=data.description,
        strategy=data.strategy,
        steps=[s.model_dump() for s in data.steps],
        variables=[v.model_dump() for v in data.variables],
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def update_template(db: AsyncSession, template_id: str, data: PlanTemplateUpdate) -> PlanTemplate | None:
    template = await get_template(db, template_id)
    if not template:
        return None
    if data.name is not None:
        template.name = data.name
    if data.description is not None:
        template.description = data.description
    if data.strategy is not None:
        template.strategy = data.strategy
    if data.steps is not None:
        template.steps = [s.model_dump() for s in data.steps]
    if data.variables is not None:
        template.variables = [v.model_dump() for v in data.variables]
    await db.commit()
    await db.refresh(template)
    return template


async def delete_template(db: AsyncSession, template_id: str) -> bool:
    template = await get_template(db, template_id)
    if not template or template.is_builtin:
        return False
    await db.delete(template)
    await db.commit()
    return True


async def apply_template(db: AsyncSession, template_id: str, data: PlanTemplateApplyRequest) -> list[dict] | None:
    template = await get_template(db, template_id)
    if not template:
        return None

    steps = template.steps or []
    variables = data.variables or {}

    def replace_vars(text: str) -> str:
        return re.sub(r'\{\{(\w+)\}\}', lambda m: variables.get(m.group(1), ''), text)

    applied = []
    for step in steps:
        applied.append({
            "prompt": replace_vars(step.get("prompt", "")),
            "negative_prompt": replace_vars(step.get("negative_prompt", "")),
            "description": replace_vars(step.get("description", "")),
            "image_count": step.get("image_count", 1),
            "image_size": step.get("image_size", ""),
        })

    return applied


_BUILTIN_TEMPLATES = [
    {
        "name": "通用设计",
        "description": "从概念到精修的通用迭代设计流程。适用于角色、物品、场景等主题。",
        "strategy": "iterative",
        "is_builtin": True,
        "variables": [
            {"key": "subject", "type": "string", "label": "设计主题", "default": "", "required": True},
            {"key": "style", "type": "string", "label": "美术风格", "default": "digital art"},
        ],
        "steps": [
            {"prompt": "Design concept of {{subject}}, {{style}}, draft, composition exploration", "negative_prompt": "blurry, low quality, deformed", "description": "概念设计", "image_count": 2, "image_size": ""},
            {"prompt": "Refined design of {{subject}}, {{style}}, detailed, high quality, polished", "negative_prompt": "blurry, low quality, deformed, inconsistent", "description": "精修设计", "image_count": 1, "image_size": ""},
            {"prompt": "Final variation of {{subject}}, {{style}}, different presentation, showcase quality", "negative_prompt": "blurry, low quality, deformed", "description": "最终展示", "image_count": 2, "image_size": ""},
        ],
    },
    {
        "name": "套图生成",
        "description": "生成风格统一的多子项套图。先生成风格锚点网格图再逐项生成，防止风格跑偏。",
        "strategy": "radiate",
        "is_builtin": True,
        "variables": [
            {"key": "items", "type": "array", "label": "子项列表", "default": [], "required": True},
            {"key": "style", "type": "string", "label": "整体风格", "default": "", "required": True},
            {"key": "overall_theme", "type": "string", "label": "主题描述", "default": ""},
        ],
        "steps": [
            {"role": "anchor", "description": "风格锚点网格图", "prompt": "A grid layout showing all items in a unified {style} style. {overall_theme}. Each cell clearly separated, consistent style throughout.", "image_count": 1, "image_size": ""},
            {"role": "expand", "description": "逐项生图", "prompt": "{item.prompt}. {style} style., consistent with reference grid.", "image_count": 1, "image_size": "", "repeat": "items", "reference_step_indices": [0]},
        ],
    },
    {
        "name": "迭代精修",
        "description": "从基础构图逐步精修到色彩和光影",
        "strategy": "iterative",
        "is_builtin": True,
        "variables": [
            {"key": "subject", "type": "string", "label": "主体描述", "default": "", "required": True},
            {"key": "style", "type": "string", "label": "风格", "default": "digital art"},
        ],
        "steps": [
            {"prompt": "{{subject}}, {{style}}, basic composition, draft quality", "negative_prompt": "blurry, low quality", "description": "基础构图", "image_count": 1, "image_size": ""},
            {"prompt": "Enhanced version with rich colors and atmosphere, {{style}}, vibrant, detailed", "negative_prompt": "blurry, low quality, dull colors", "description": "色彩精修", "image_count": 1, "image_size": ""},
            {"prompt": "Final polished version with dramatic lighting and cinematic atmosphere, {{style}}, masterpiece", "negative_prompt": "blurry, low quality, flat lighting", "description": "光影精修", "image_count": 1, "image_size": ""},
        ],
    },
]


async def seed_builtin_templates(db: AsyncSession):
    from sqlalchemy import text
    for tmpl in _BUILTIN_TEMPLATES:
        result = await db.execute(
            text("SELECT id FROM plan_templates WHERE name = :name AND is_builtin = 1"),
            {"name": tmpl["name"]},
        )
        if result.fetchone():
            continue
        template = PlanTemplate(
            name=tmpl["name"],
            description=tmpl["description"],
            strategy=tmpl["strategy"],
            steps=tmpl["steps"],
            variables=tmpl["variables"],
            is_builtin=tmpl["is_builtin"],
        )
        db.add(template)
    await db.commit()
