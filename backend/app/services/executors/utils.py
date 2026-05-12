from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_provider import ApiProvider
from app.schemas.execution import ExecutionPlan
from app.schemas.planning import PlanningContext
from app.utils.image_client import ImageClient


async def get_provider(db: AsyncSession, provider_id: str) -> ApiProvider | None:
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    return result.scalar_one_or_none()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def resolve_context_references(plan: ExecutionPlan, context: PlanningContext) -> list[str] | None:
    all_refs: list[str] = list(context.reference_images or [])
    context_urls = plan.plan_meta.get("context_reference_urls", [])
    if context_urls:
        try:
            url_b64 = await ImageClient.urls_to_base64(context_urls[:4])
            all_refs.extend(url_b64)
        except Exception:
            pass
    return all_refs[:4] if all_refs else None
