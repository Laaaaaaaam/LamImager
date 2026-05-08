import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import gen_uuid, now


class ProviderType(str, enum.Enum):
    image_gen = "image_gen"
    llm = "llm"
    web_search = "web_search"


class BillingType(str, enum.Enum):
    per_call = "per_call"
    per_token = "per_token"


class ApiProvider(Base):
    __tablename__ = "api_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    nickname: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    api_key_enc: Mapped[str] = mapped_column(Text, nullable=False)
    provider_type: Mapped[str] = mapped_column(Enum(ProviderType), nullable=False)
    billing_type: Mapped[str] = mapped_column(Enum(BillingType), default=BillingType.per_call)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    billing_records = relationship("BillingRecord", back_populates="provider")
