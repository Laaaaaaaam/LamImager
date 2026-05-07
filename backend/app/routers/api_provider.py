from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.api_provider import ProviderType
from app.schemas.api_provider import (
    ApiProviderCreate,
    ApiProviderResponse,
    ApiProviderTestResult,
    ApiProviderUpdate,
)
from app.services.api_manager import (
    create_provider,
    delete_provider,
    get_provider,
    list_providers,
    provider_to_response,
    test_connection,
    update_provider,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.post("", response_model=ApiProviderResponse)
async def api_create_provider(data: ApiProviderCreate, db: AsyncSession = Depends(get_db)):
    provider = await create_provider(db, data)
    return provider_to_response(provider)


@router.get("", response_model=list[ApiProviderResponse])
async def api_list_providers(
    provider_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    pt = None
    if provider_type:
        try:
            pt = ProviderType(provider_type)
        except ValueError:
            pass
    providers = await list_providers(db, pt)
    return [provider_to_response(p) for p in providers]


@router.get("/{provider_id}", response_model=ApiProviderResponse)
async def api_get_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    provider = await get_provider(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider_to_response(provider)


@router.put("/{provider_id}", response_model=ApiProviderResponse)
async def api_update_provider(
    provider_id: str, data: ApiProviderUpdate, db: AsyncSession = Depends(get_db)
):
    provider = await update_provider(db, provider_id, data)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider_to_response(provider)


@router.delete("/{provider_id}")
async def api_delete_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    success = await delete_provider(db, provider_id)
    if not success:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"message": "Provider deleted"}


@router.post("/{provider_id}/test", response_model=ApiProviderTestResult)
async def api_test_connection(provider_id: str, db: AsyncSession = Depends(get_db)):
    result = await test_connection(db, provider_id)
    return ApiProviderTestResult(**result)
