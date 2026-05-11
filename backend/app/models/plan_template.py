from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import gen_uuid, now


class PlanTemplate(Base):
    __tablename__ = "plan_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    strategy: Mapped[str] = mapped_column(String(20), default="parallel")
    steps: Mapped[dict] = mapped_column(JSON, default=list)
    variables: Mapped[dict] = mapped_column(JSON, default=dict)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    builtin_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
