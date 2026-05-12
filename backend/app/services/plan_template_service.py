from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan_template import PlanTemplate
from app.schemas.execution import ExecutionPlan, PlanStep
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


_ALLOWED_STRATEGIES = {"parallel", "iterative", "radiate"}


def _validate_strategy(strategy: str):
    if strategy not in _ALLOWED_STRATEGIES:
        raise ValueError(f"无效策略: {strategy}，允许值: {', '.join(sorted(_ALLOWED_STRATEGIES))}")


async def create_template(db: AsyncSession, data: PlanTemplateCreate) -> PlanTemplate:
    _validate_strategy(data.strategy)
    if not data.steps:
        raise ValueError("模板必须包含至少 1 个步骤")
    for i, s in enumerate(data.steps):
        if not s.prompt.strip():
            raise ValueError(f"步骤 {i+1} 缺少 prompt 字段")
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
        _validate_strategy(data.strategy)
        template.strategy = data.strategy
    if data.steps is not None:
        if not data.steps:
            raise ValueError("模板必须包含至少 1 个步骤")
        for i, s in enumerate(data.steps):
            if not s.prompt.strip():
                raise ValueError(f"步骤 {i+1} 缺少 prompt 字段")
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


async def apply_template(db: AsyncSession, template_id: str, data: PlanTemplateApplyRequest) -> ExecutionPlan | None:
    template = await get_template(db, template_id)
    if not template:
        return None

    steps = template.steps or []
    variables = data.variables or {}

    merged_vars = {}
    missing_required = []
    for var_def in (template.variables or []):
        key = var_def.get("key", "")
        if not key:
            continue
        merged_vars[key] = var_def.get("default", "")
        if var_def.get("required"):
            missing_required.append(key)
    merged_vars.update(variables)

    for key in missing_required:
        if not merged_vars.get(key):
            label = next((v.get("label", key) for v in (template.variables or []) if v.get("key") == key), key)
            raise ValueError(f"缺少必填变量: {label}")

    def replace_vars(text: str) -> str:
        return re.sub(r'\{\{([\w.]+)\}\}', lambda m: merged_vars.get(m.group(1), ''), text)

    plan_steps: list[PlanStep] = []
    for i, step in enumerate(steps):
        plan_steps.append(PlanStep(
            index=i,
            prompt=replace_vars(step.get("prompt", "")),
            negative_prompt=replace_vars(step.get("negative_prompt", "")),
            description=replace_vars(step.get("description", "")),
            image_count=step.get("image_count", 1),
            image_size=step.get("image_size", ""),
            reference_step_indices=step.get("reference_step_indices"),
            checkpoint=step.get("checkpoint"),
            condition=step.get("condition"),
            role=step.get("role", ""),
            repeat=step.get("repeat", ""),
        ))

    plan_meta: dict = {"template_id": template.id, "template_name": template.name}
    if template.strategy == "radiate":
        plan_meta["items"] = variables.get("items", [])
        plan_meta["style"] = variables.get("style", "")
        plan_meta["overall_theme"] = variables.get("overall_theme", "")

    return ExecutionPlan(
        strategy=template.strategy,
        steps=plan_steps,
        source="template",
        plan_meta=plan_meta,
    )


_BUILTIN_TEMPLATES = [
    {
        "name": "通用设计",
        "description": "从概念到精修的通用迭代设计流程。适用于角色、物品、场景等主题。",
        "strategy": "iterative",
        "is_builtin": True,
        "builtin_version": 1,
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
        "description": "生成风格统一的多子项套图。先生成4096x4096风格锚点网格图再逐项生成，防止跑偏。",
        "strategy": "radiate",
        "is_builtin": True,
        "builtin_version": 1,
        "variables": [
            {"key": "items", "type": "array", "label": "子项列表", "default": [], "required": True},
            {"key": "style", "type": "string", "label": "整体风格", "default": "", "required": True},
            {"key": "overall_theme", "type": "string", "label": "主题描述", "default": ""},
        ],
        "steps": [
            {"role": "anchor", "description": "风格锚点网格图(4096x4096)", "prompt": "A grid layout showing all items in a unified {{style}} style. {{overall_theme}}. Each cell clearly separated, consistent style throughout.", "image_count": 1, "image_size": "4096x4096"},
            {"role": "expand", "description": "逐项生图", "prompt": "{{item.prompt}}. {{style}} style., consistent with reference grid.", "image_count": 1, "image_size": "", "repeat": "items", "reference_step_indices": [0]},
        ],
    },
    {
        "name": "迭代精修",
        "description": "从基础构图逐步精修到色彩和光影",
        "strategy": "iterative",
        "is_builtin": True,
        "builtin_version": 1,
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
        builtin_version = tmpl.get("builtin_version", 1)
        result = await db.execute(
            text("SELECT id, builtin_version FROM plan_templates WHERE name = :name AND is_builtin = 1"),
            {"name": tmpl["name"]},
        )
        row = result.fetchone()
        if row and (row[1] or 0) >= builtin_version:
            continue
        if row:
            await db.execute(
                text("UPDATE plan_templates SET description=:desc, strategy=:strat, steps=:steps, variables=:vars, builtin_version=:ver, updated_at=datetime('now') WHERE id=:id"),
                {"desc": tmpl["description"], "strat": tmpl["strategy"], "steps": json.dumps(tmpl["steps"]), "vars": json.dumps(tmpl["variables"]), "ver": builtin_version, "id": row[0]},
            )
        else:
            template = PlanTemplate(
                name=tmpl["name"],
                description=tmpl["description"],
                strategy=tmpl["strategy"],
                steps=tmpl["steps"],
                variables=tmpl["variables"],
                is_builtin=tmpl["is_builtin"],
                builtin_version=builtin_version,
            )
            db.add(template)
    await db.commit()
