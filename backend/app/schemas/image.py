from __future__ import annotations

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    dir: str = Field(min_length=1)
    recursive: bool = False


class ImageItem(BaseModel):
    path: str
    name: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    thumb_url: str
    valid: bool
    reason: str | None = None


class ScanResponse(BaseModel):
    root: str
    items: list[ImageItem]
    total_seen: int
    truncated: bool


class UploadResponse(BaseModel):
    upload_dir: str
    items: list[ImageItem]
