from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from loguru import logger

from app.core.settings import get_settings
from app.schemas.image import ImageItem, ScanRequest, ScanResponse, UploadResponse
from app.services.storage import (
    ALLOWED_EXTS,
    InvalidPathError,
    ensure_thumbnail,
    scan_directory,
    thumb_url_of,
)

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/scan", response_model=ScanResponse)
async def scan(payload: ScanRequest) -> ScanResponse:
    try:
        items, total, truncated = scan_directory(payload.dir, recursive=payload.recursive)
    except InvalidPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScanResponse(
        root=payload.dir,
        items=[
            ImageItem(
                path=i.path,
                name=i.name,
                size_bytes=i.size_bytes,
                width=i.width,
                height=i.height,
                thumb_url=i.thumb_url,
                valid=i.valid,
                reason=i.reason,
            )
            for i in items
        ],
        total_seen=total,
        truncated=truncated,
    )


def _make_upload_dir() -> Path:
    s = get_settings()
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:8]
    target = s.APP_DATA_DIR / "uploads" / f"{ts}_{short_id}"
    target.mkdir(parents=True, exist_ok=True)
    return target


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload(files: list[UploadFile]) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")

    s = get_settings()
    if len(files) > 200:
        raise HTTPException(status_code=400, detail="too many files (max 200)")

    target = _make_upload_dir()
    items: list[ImageItem] = []

    for f in files:
        if not f.filename:
            continue
        suffix = Path(f.filename).suffix.lower()
        if suffix not in ALLOWED_EXTS:
            logger.info("skip non-image upload: {}", f.filename)
            continue
        # 内容大小检查（流式拷贝时累计）
        dst = target / Path(f.filename).name
        size = 0
        with dst.open("wb") as out:
            while True:
                chunk = await f.read(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > s.UPLOAD_MAX_BYTES:
                    out.close()
                    dst.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"file '{f.filename}' exceeds {s.UPLOAD_MAX_BYTES} bytes",
                    )
                out.write(chunk)
        # 嗅探尺寸
        from PIL import Image, UnidentifiedImageError

        valid = True
        reason: str | None = None
        w: int | None = None
        h: int | None = None
        try:
            with Image.open(dst) as im:
                w, h = im.size
        except (OSError, UnidentifiedImageError):
            valid = False
            reason = "unrecognized image"

        if valid:
            ensure_thumbnail(dst)

        items.append(
            ImageItem(
                path=dst.resolve().as_posix(),
                name=dst.name,
                size_bytes=size,
                width=w,
                height=h,
                thumb_url=thumb_url_of(dst) if valid else "",
                valid=valid,
                reason=reason,
            )
        )

    return UploadResponse(upload_dir=target.as_posix(), items=items)
