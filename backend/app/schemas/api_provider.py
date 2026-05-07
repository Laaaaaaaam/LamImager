from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.api_provider import BillingType, ProviderType


class ApiProviderCreate(BaseModel):
    nickname: str
    base_url: str
    model_id: str
    api_key: str
    provider_type: ProviderType
    billing_type: BillingType = BillingType.per_call
    unit_price: float = 0
    currency: str = "CNY"
    is_active: bool = True


class ApiProviderUpdate(BaseModel):
    nickname: str | None = None
    base_url: str | None = None
    model_id: str | None = None
    api_key: str | None = None
    provider_type: ProviderType | None = None
    billing_type: BillingType | None = None
    unit_price: float | None = None
    currency: str | None = None
    is_active: bool | None = None


class ApiProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nickname: str
    base_url: str
    model_id: str
    api_key_masked: str = ""
    provider_type: str
    billing_type: str
    unit_price: float
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ApiProviderTestResult(BaseModel):
    success: bool
    message: str = ""
