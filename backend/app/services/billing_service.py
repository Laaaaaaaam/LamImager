import csv
import io
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import now
from app.models.billing import BillingRecord
from app.schemas.billing import BillingDetailQuery, BillingRecordResponse, BillingSummary


async def record_billing(
    db: AsyncSession,
    session_id: str = None,
    provider_id: str = None,
    billing_type: str = "per_call",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost: float = 0,
    currency: str = "CNY",
    detail: dict = None,
) -> BillingRecord:
    record = BillingRecord(
        session_id=session_id,
        provider_id=provider_id,
        billing_type=billing_type,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
        currency=currency,
        detail=detail or {},
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_summary(db: AsyncSession) -> BillingSummary:
    _now = now()
    today_start = _now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = _now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_result = await db.execute(select(func.sum(BillingRecord.cost)))
    total = float(total_result.scalar() or 0)

    today_result = await db.execute(
        select(func.sum(BillingRecord.cost)).where(BillingRecord.created_at >= today_start)
    )
    today = float(today_result.scalar() or 0)

    month_result = await db.execute(
        select(func.sum(BillingRecord.cost)).where(BillingRecord.created_at >= month_start)
    )
    month = float(month_result.scalar() or 0)

    return BillingSummary(today=today, month=month, total=total)


async def get_details(db: AsyncSession, query: BillingDetailQuery) -> dict:
    q = select(BillingRecord)

    if query.start_date:
        q = q.where(BillingRecord.created_at >= datetime.fromisoformat(query.start_date))
    if query.end_date:
        q = q.where(BillingRecord.created_at <= datetime.fromisoformat(query.end_date))
    if query.provider_id:
        q = q.where(BillingRecord.provider_id == query.provider_id)
    if query.session_id:
        q = q.where(BillingRecord.session_id == query.session_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar() or 0

    q = q.order_by(BillingRecord.created_at.desc())
    q = q.offset((query.page - 1) * query.page_size).limit(query.page_size)

    result = await db.execute(q)
    records = list(result.scalars().all())

    return {
        "total": total,
        "page": query.page,
        "page_size": query.page_size,
        "records": [billing_to_response(r) for r in records],
    }


async def export_billing_csv(db: AsyncSession, query: BillingDetailQuery) -> str:
    q = select(BillingRecord)

    if query.start_date:
        q = q.where(BillingRecord.created_at >= datetime.fromisoformat(query.start_date))
    if query.end_date:
        q = q.where(BillingRecord.created_at <= datetime.fromisoformat(query.end_date))

    result = await db.execute(q.order_by(BillingRecord.created_at.desc()))
    records = list(result.scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Session ID", "Provider ID", "Type", "Tokens In", "Tokens Out", "Cost", "Currency", "Created At"])
    for r in records:
        writer.writerow([
            r.id, r.session_id or "", r.provider_id or "",
            r.billing_type.value if hasattr(r.billing_type, "value") else r.billing_type,
            r.tokens_in, r.tokens_out, float(r.cost) if r.cost else 0,
            r.currency, r.created_at.isoformat() if r.created_at else "",
        ])

    return output.getvalue()


def billing_to_response(record: BillingRecord) -> dict:
    return {
        "id": record.id,
        "session_id": record.session_id,
        "provider_id": record.provider_id,
        "billing_type": record.billing_type.value if hasattr(record.billing_type, "value") else record.billing_type,
        "tokens_in": record.tokens_in,
        "tokens_out": record.tokens_out,
        "cost": float(record.cost) if record.cost else 0,
        "currency": record.currency,
        "detail": record.detail or {},
        "created_at": record.created_at,
    }
