from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("code", name="uq_templates_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    default_size: Mapped[str | None] = mapped_column(String(32), nullable=True)
    builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
