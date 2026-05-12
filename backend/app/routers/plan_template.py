from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.plan_template import (
    PlanTemplateCreate,
    PlanTemplateUpdate,
    PlanTemplateResponse,
    PlanTemplateApplyRequest,
)
from app.services.plan_template_service import (
    list_templates,
    get_template,
    create_template,
    update_template,
    delete_template,
    apply_template,
)

router = APIRouter(prefix="/api/plan-templates", tags=["plan-templates"])


@router.get("", response_model=list[PlanTemplateResponse])
async def api_list_templates(db: AsyncSession = Depends(get_db)):
    return await list_templates(db)


@router.get("/{template_id}", response_model=PlanTemplateResponse)
async def api_get_template(template_id: str, db: AsyncSession = Depends(get_db)):
    template = await get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("", response_model=PlanTemplateResponse)
async def api_create_template(data: PlanTemplateCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await create_template(db, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/{template_id}", response_model=PlanTemplateResponse)
async def api_update_template(template_id: str, data: PlanTemplateUpdate, db: AsyncSession = Depends(get_db)):
    try:
        template = await update_template(db, template_id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.delete("/{template_id}")
async def api_delete_template(template_id: str, db: AsyncSession = Depends(get_db)):
    success = await delete_template(db, template_id)
    if not success:
        raise HTTPException(status_code=404, detail="Template not found or is built-in")
    return {"message": "Template deleted"}


@router.post("/{template_id}/apply")
async def api_apply_template(template_id: str, data: PlanTemplateApplyRequest, db: AsyncSession = Depends(get_db)):
    try:
        plan = await apply_template(db, template_id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if plan is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return {
        "plan": plan.model_dump(),
        "steps": plan.to_steps_dict(),
        "strategy": plan.strategy,
    }
