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
        "name": "产品展示套图",
        "description": "生成产品的正面/侧面/细节/场景展示图",
        "strategy": "parallel",
        "is_builtin": True,
        "variables": [
            {"key": "product", "type": "string", "label": "产品名称", "default": "", "required": True},
            {"key": "style", "type": "string", "label": "风格", "default": "modern minimalist"},
            {"key": "background", "type": "string", "label": "背景", "default": "white studio background"},
        ],
        "steps": [
            {"prompt": "Front view of {{product}}, {{style}}, {{background}}, product photography, 8k", "negative_prompt": "blurry, low quality, distorted", "description": "正面展示", "image_count": 1, "image_size": ""},
            {"prompt": "Side view of {{product}}, {{style}}, {{background}}, product photography, 8k", "negative_prompt": "blurry, low quality, distorted", "description": "侧面展示", "image_count": 1, "image_size": ""},
            {"prompt": "Close-up detail of {{product}}, {{style}}, macro photography, {{background}}, 8k", "negative_prompt": "blurry, low quality, distorted", "description": "细节特写", "image_count": 1, "image_size": ""},
            {"prompt": "{{product}} in lifestyle scene, {{style}}, natural lighting, lifestyle photography, 8k", "negative_prompt": "blurry, low quality, distorted", "description": "场景展示", "image_count": 1, "image_size": ""},
        ],
    },
    {
        "name": "角色设计",
        "description": "生成角色概念设计、精修和变体图",
        "strategy": "iterative",
        "is_builtin": True,
        "variables": [
            {"key": "character", "type": "string", "label": "角色描述", "default": "", "required": True},
            {"key": "art_style", "type": "string", "label": "美术风格", "default": "anime style"},
            {"key": "pose", "type": "string", "label": "姿势", "default": "standing"},
        ],
        "steps": [
            {"prompt": "Character design concept of {{character}}, {{art_style}}, {{pose}}, full body, character sheet", "negative_prompt": "blurry, low quality, deformed", "description": "概念设计", "image_count": 2, "image_size": ""},
            {"prompt": "Refined character design of {{character}}, {{art_style}}, detailed, high quality", "negative_prompt": "blurry, low quality, deformed, inconsistent", "description": "精修设计", "image_count": 1, "image_size": ""},
            {"prompt": "Character variation of {{character}}, {{art_style}}, different angle, {{pose}}", "negative_prompt": "blurry, low quality, deformed", "description": "角度变体", "image_count": 2, "image_size": ""},
        ],
    },
    {
        "name": "四季风景",
        "description": "生成同一场景的春/夏/秋/冬四张风景图",
        "strategy": "parallel",
        "is_builtin": True,
        "variables": [
            {"key": "scene", "type": "string", "label": "场景描述", "default": "a peaceful lake with mountains", "required": True},
            {"key": "art_style", "type": "string", "label": "风格", "default": "photorealistic landscape photography"},
        ],
        "steps": [
            {"prompt": "{{scene}} in spring, cherry blossoms, fresh green, warm sunlight, {{art_style}}, 8k", "negative_prompt": "blurry, low quality", "description": "春", "image_count": 1, "image_size": ""},
            {"prompt": "{{scene}} in summer, lush green, bright blue sky, golden sunlight, {{art_style}}, 8k", "negative_prompt": "blurry, low quality", "description": "夏", "image_count": 1, "image_size": ""},
            {"prompt": "{{scene}} in autumn, red and golden leaves, misty atmosphere, {{art_style}}, 8k", "negative_prompt": "blurry, low quality", "description": "秋", "image_count": 1, "image_size": ""},
            {"prompt": "{{scene}} in winter, snow covered, frozen lake, soft cold light, {{art_style}}, 8k", "negative_prompt": "blurry, low quality", "description": "冬", "image_count": 1, "image_size": ""},
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
