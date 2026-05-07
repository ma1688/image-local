from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ApiProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=512)
    default_model: str | None = None


class ApiProfileCreate(ApiProfileBase):
    api_key: str = Field(min_length=1, max_length=2048)


class ApiProfileUpdate(BaseModel):
    """所有字段可选；api_key 为空字符串视为不修改 Key。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    default_model: str | None = None
    api_key: str | None = None


class ApiProfileRead(ApiProfileBase):
    """对外返回；api_key_masked 形如 ****abcd。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    api_key_masked: str
    created_at: datetime
    updated_at: datetime


class ModelInfo(BaseModel):
    id: str
    object: str | None = None
    owned_by: str | None = None


class ModelListResponse(BaseModel):
    models: list[ModelInfo]


def _sanitize_url(url: str) -> str:
    """轻量校验：URL 必须能被 HttpUrl 解析。返回去除尾部 / 的字符串。"""
    HttpUrl(url)
    return url.rstrip("/")
