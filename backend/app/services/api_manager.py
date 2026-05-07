from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import now
from app.models.api_provider import ApiProvider, ProviderType
from app.schemas.api_provider import ApiProviderCreate, ApiProviderUpdate
from app.utils.crypto import decrypt, encrypt, mask_key
from app.utils.llm_client import LLMClient
from app.utils.image_client import ImageClient


async def create_provider(db: AsyncSession, data: ApiProviderCreate) -> ApiProvider:
    provider = ApiProvider(
        nickname=data.nickname,
        base_url=data.base_url,
        model_id=data.model_id,
        api_key_enc=encrypt(data.api_key),
        provider_type=data.provider_type,
        billing_type=data.billing_type,
        unit_price=data.unit_price,
        currency=data.currency,
        is_active=data.is_active,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider


async def update_provider(db: AsyncSession, provider_id: str, data: ApiProviderUpdate) -> ApiProvider:
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "api_key" in update_data:
        update_data["api_key_enc"] = encrypt(update_data.pop("api_key"))
    else:
        update_data.pop("api_key", None)

    for key, value in update_data.items():
        setattr(provider, key, value)

    provider.updated_at = now()
    await db.commit()
    await db.refresh(provider)
    return provider


async def delete_provider(db: AsyncSession, provider_id: str) -> bool:
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        return False
    await db.delete(provider)
    await db.commit()
    return True


async def get_provider(db: AsyncSession, provider_id: str) -> ApiProvider:
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    return result.scalar_one_or_none()


async def list_providers(db: AsyncSession, provider_type: str = None) -> list[ApiProvider]:
    query = select(ApiProvider)
    if provider_type:
        query = query.where(ApiProvider.provider_type == provider_type)
    result = await db.execute(query.order_by(ApiProvider.created_at.desc()))
    return list(result.scalars().all())


async def test_connection(db: AsyncSession, provider_id: str) -> dict:
    provider = await get_provider(db, provider_id)
    if not provider:
        return {"success": False, "message": "Provider not found"}

    api_key = decrypt(provider.api_key_enc)
    try:
        if provider.provider_type == ProviderType.llm:
            client = LLMClient(provider.base_url, api_key, provider.model_id)
            success = await client.test_connection()
        else:
            client = ImageClient(provider.base_url, api_key, provider.model_id)
            success = await client.test_connection()

        return {
            "success": success,
            "message": "Connection successful" if success else "Connection failed",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def provider_to_response(provider: ApiProvider) -> dict:
    api_key_masked = mask_key(decrypt(provider.api_key_enc)) if provider.api_key_enc else ""
    return {
        "id": provider.id,
        "nickname": provider.nickname,
        "base_url": provider.base_url,
        "model_id": provider.model_id,
        "api_key_masked": api_key_masked,
        "provider_type": provider.provider_type.value if hasattr(provider.provider_type, "value") else provider.provider_type,
        "billing_type": provider.billing_type.value if hasattr(provider.billing_type, "value") else provider.billing_type,
        "unit_price": float(provider.unit_price) if provider.unit_price else 0,
        "currency": provider.currency,
        "is_active": provider.is_active,
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }
