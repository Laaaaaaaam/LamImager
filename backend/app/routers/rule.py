from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.rule import RuleCreate, RuleResponse, RuleUpdate
from app.services.rule_engine import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    rule_to_response,
    toggle_rule,
    update_rule,
)

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.post("", response_model=RuleResponse)
async def api_create_rule(data: RuleCreate, db: AsyncSession = Depends(get_db)):
    rule = await create_rule(db, data)
    return rule_to_response(rule)


@router.get("", response_model=list[RuleResponse])
async def api_list_rules(
    rule_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    rules = await list_rules(db, rule_type)
    return [rule_to_response(r) for r in rules]


@router.get("/{rule_id}", response_model=RuleResponse)
async def api_get_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    rule = await get_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule_to_response(rule)


@router.put("/{rule_id}", response_model=RuleResponse)
async def api_update_rule(
    rule_id: str, data: RuleUpdate, db: AsyncSession = Depends(get_db)
):
    rule = await update_rule(db, rule_id, data)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule_to_response(rule)


@router.delete("/{rule_id}")
async def api_delete_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    success = await delete_rule(db, rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Rule deleted"}


@router.put("/{rule_id}/toggle", response_model=RuleResponse)
async def api_toggle_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    rule = await toggle_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule_to_response(rule)
