from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TemplateBase(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    prompt_template: str = ""
    default_model: str | None = None
    default_size: str | None = None


class TemplateCreate(TemplateBase):
    pass


class TemplateRead(TemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    builtin: bool
    created_at: datetime
