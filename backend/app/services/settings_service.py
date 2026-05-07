from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import now
from app.models.app_setting import AppSetting


async def get_setting(db: AsyncSession, key: str) -> dict | None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if not setting:
        return None
    return setting.value


async def set_setting(db: AsyncSession, key: str, value: dict) -> AppSetting:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
        setting.updated_at = now()
    else:
        setting = AppSetting(key=key, value=value)
        db.add(setting)
    await db.commit()
    await db.refresh(setting)
    return setting


async def get_default_models(db: AsyncSession) -> dict:
    result = {}
    for key in ["default_optimize_provider_id", "default_image_provider_id", "default_plan_provider_id"]:
        val = await get_setting(db, key)
        if val and isinstance(val, dict):
            result[key] = val.get("provider_id")
        else:
            result[key] = None

    width_val = await get_setting(db, "default_image_width")
    result["default_image_width"] = width_val.get("value", 1024) if width_val else 1024

    height_val = await get_setting(db, "default_image_height")
    result["default_image_height"] = height_val.get("value", 1024) if height_val else 1024

    concurrent_val = await get_setting(db, "max_concurrent")
    result["max_concurrent"] = concurrent_val.get("value", 5) if concurrent_val else 5

    return result


async def set_default_models(db: AsyncSession, config: dict) -> dict:
    for key in ["default_optimize_provider_id", "default_image_provider_id", "default_plan_provider_id"]:
        if key in config:
            if config[key]:
                await set_setting(db, key, {"provider_id": config[key]})
            else:
                existing = await db.execute(select(AppSetting).where(AppSetting.key == key))
                setting = existing.scalar_one_or_none()
                if setting:
                    await db.delete(setting)
                    await db.commit()

    if "default_image_width" in config:
        await set_setting(db, "default_image_width", {"value": config["default_image_width"]})

    if "default_image_height" in config:
        await set_setting(db, "default_image_height", {"value": config["default_image_height"]})

    if "max_concurrent" in config:
        await set_setting(db, "max_concurrent", {"value": config["max_concurrent"]})

    return await get_default_models(db)
