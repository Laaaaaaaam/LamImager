from __future__ import annotations
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule import Rule, RuleType
from app.schemas.rule import RuleCreate, RuleUpdate


async def create_rule(db: AsyncSession, data: RuleCreate) -> Rule:
    rule = Rule(
        name=data.name,
        rule_type=data.rule_type,
        config=data.config,
        is_active=data.is_active,
        priority=data.priority,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def update_rule(db: AsyncSession, rule_id: str, data: RuleUpdate) -> Rule | None:
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)

    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, rule_id: str) -> bool:
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        return False
    await db.delete(rule)
    await db.commit()
    return True


async def get_rule(db: AsyncSession, rule_id: str) -> Rule | None:
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    return result.scalar_one_or_none()


async def list_rules(db: AsyncSession, rule_type: str = None) -> list[Rule]:
    query = select(Rule)
    if rule_type:
        query = query.where(Rule.rule_type == rule_type)
    result = await db.execute(query.order_by(Rule.priority.desc(), Rule.created_at.desc()))
    return list(result.scalars().all())


async def toggle_rule(db: AsyncSession, rule_id: str) -> Rule | None:
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        return None
    rule.is_active = not rule.is_active
    await db.commit()
    await db.refresh(rule)
    return rule


async def get_active_rules(db: AsyncSession, rule_type: str = None) -> list[Rule]:
    query = select(Rule).where(Rule.is_active == True)
    if rule_type:
        query = query.where(Rule.rule_type == rule_type)
    result = await db.execute(query.order_by(Rule.priority.desc()))
    return list(result.scalars().all())


def apply_rules(context: dict, rules: list[Rule]) -> dict:
    result = dict(context)
    for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
        if not rule.is_active:
            continue
        config = rule.config or {}
        if rule.rule_type == RuleType.default_params:
            for key, value in config.items():
                if key not in result or result[key] is None:
                    result[key] = value
        elif rule.rule_type == RuleType.filter:
            if "negative_keywords" in config:
                existing = result.get("negative_prompt", "")
                keywords = ", ".join(config["negative_keywords"])
                result["negative_prompt"] = f"{existing}, {keywords}".strip(", ")
        elif rule.rule_type == RuleType.workflow:
            if "pre_processing" in config:
                result.setdefault("workflow_steps", []).extend(config["pre_processing"])
    return result


def rule_to_response(rule: Rule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "rule_type": rule.rule_type.value if hasattr(rule.rule_type, "value") else rule.rule_type,
        "config": rule.config or {},
        "is_active": rule.is_active,
        "priority": rule.priority,
        "created_at": rule.created_at,
    }
