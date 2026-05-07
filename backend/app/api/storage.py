"""存储使用情况 API：报告 outputs/uploads/thumbs 子目录占用、磁盘剩余、警戒阈值。

仅做"读取 + 警告"，不做自动清理；自动清理涉及策略和数据可见性，留给后续。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.settings import get_settings

router = APIRouter(prefix="/storage", tags=["storage"])


class StorageBucket(BaseModel):
    name: str
    path: str
    bytes: int
    files: int


class StorageUsageResponse(BaseModel):
    data_dir: str
    total_bytes: int
    buckets: list[StorageBucket]
    disk_total_bytes: int
    disk_free_bytes: int
    warn_bytes: int
    hard_limit_bytes: int
    status: str  # ok / warn / critical


def _dir_usage(path: Path) -> tuple[int, int]:
    """返回 (size_bytes, file_count)；不存在 -> (0, 0)。
    遵循 followlinks=False 与 os.walk 一致，避免符号链接环。
    """
    if not path.exists():
        return 0, 0
    total = 0
    files = 0
    for p in path.rglob("*"):
        if p.is_symlink():
            continue
        try:
            if p.is_file():
                total += p.stat().st_size
                files += 1
        except OSError:
            continue
    return total, files


@router.get("/usage", response_model=StorageUsageResponse)
async def storage_usage() -> StorageUsageResponse:
    s = get_settings()
    data_dir = s.APP_DATA_DIR

    bucket_paths = {
        "outputs": data_dir / "outputs",
        "uploads": data_dir / "uploads",
        "thumbs": data_dir / "thumbs",
    }
    buckets: list[StorageBucket] = []
    total = 0
    for name, p in bucket_paths.items():
        size, count = _dir_usage(p)
        total += size
        buckets.append(
            StorageBucket(name=name, path=p.as_posix(), bytes=size, files=count)
        )

    try:
        disk = shutil.disk_usage(data_dir.as_posix())
        disk_total, disk_free = int(disk.total), int(disk.free)
    except OSError:
        disk_total, disk_free = 0, 0

    warn = int(s.STORAGE_WARN_BYTES)
    hard = int(s.STORAGE_HARD_LIMIT_BYTES)

    if hard > 0 and total >= hard:
        status = "critical"
    elif total >= warn:
        status = "warn"
    else:
        status = "ok"

    return StorageUsageResponse(
        data_dir=data_dir.as_posix(),
        total_bytes=total,
        buckets=buckets,
        disk_total_bytes=disk_total,
        disk_free_bytes=disk_free,
        warn_bytes=warn,
        hard_limit_bytes=hard,
        status=status,
    )
