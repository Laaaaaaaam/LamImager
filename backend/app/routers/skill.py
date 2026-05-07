from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.skill import SkillCreate, SkillImport, SkillResponse, SkillUpdate
from app.services.skill_engine import (
    create_skill,
    delete_skill,
    get_skill,
    import_skill,
    list_skills,
    skill_to_response,
    update_skill,
)

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.post("", response_model=SkillResponse)
async def api_create_skill(data: SkillCreate, db: AsyncSession = Depends(get_db)):
    skill = await create_skill(db, data)
    return skill_to_response(skill)


@router.get("", response_model=list[SkillResponse])
async def api_list_skills(db: AsyncSession = Depends(get_db)):
    skills = await list_skills(db)
    return [skill_to_response(s) for s in skills]


@router.get("/{skill_id}", response_model=SkillResponse)
async def api_get_skill(skill_id: str, db: AsyncSession = Depends(get_db)):
    skill = await get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill_to_response(skill)


@router.put("/{skill_id}", response_model=SkillResponse)
async def api_update_skill(
    skill_id: str, data: SkillUpdate, db: AsyncSession = Depends(get_db)
):
    skill = await update_skill(db, skill_id, data)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill_to_response(skill)


@router.delete("/{skill_id}")
async def api_delete_skill(skill_id: str, db: AsyncSession = Depends(get_db)):
    success = await delete_skill(db, skill_id)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"message": "Skill deleted"}


@router.post("/import", response_model=SkillResponse)
async def api_import_skill(data: SkillImport, db: AsyncSession = Depends(get_db)):
    skill = await import_skill(db, data)
    return skill_to_response(skill)
