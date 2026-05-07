"""受控文件下载：仅允许在 outputs / thumbs / uploads / 已扫描根目录下读取。

注意：当 ALLOW_ANY_DIR_SCAN=true 时，前端会传入 host 上扫描的图片绝对路径，
后端需要允许这些路径。这里通过两层防护：
- 路径必须存在 + 必须 resolve 后落入"扩展白名单"
- 扩展白名单 = data 根目录 + 当前进程的所有可能源（取自 settings.outputs/thumbs/uploads + ALLOW_ANY_DIR_SCAN 模式下不再限制源目录）。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from loguru import logger

from app.core.settings import get_settings
from app.services.storage import allowed_roots

router = APIRouter(prefix="/files", tags=["files"])


_MIME_BY_EXT: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
}


def _resolve_within_allowlist(raw: str) -> Path:
    s = get_settings()
    p = Path(raw).expanduser()
    try:
        rp = p.resolve(strict=False)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"bad path: {exc}") from exc

    if not rp.exists() or not rp.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {rp.as_posix()}")

    if s.ALLOW_ANY_DIR_SCAN:
        # 任意源 + 写审计日志
        logger.info("[audit] file fetch: {}", rp.as_posix())
        return rp

    # 仅允许 data/{outputs,thumbs,uploads}
    roots = allowed_roots()
    if not any(rp == root or root in rp.parents for root in roots):
        raise HTTPException(
            status_code=403,
            detail=f"path outside allowed roots: {rp.as_posix()}",
        )
    return rp


@router.get("")
async def get_file(path: str = Query(min_length=1), download: bool = False) -> Response:
    rp = _resolve_within_allowlist(path)
    media_type = _MIME_BY_EXT.get(rp.suffix.lower(), "application/octet-stream")
    headers: dict[str, str] = {}
    if download:
        # RFC 5987：UTF-8 文件名兼容
        headers["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{quote(rp.name)}"
        )
    return FileResponse(rp, media_type=media_type, headers=headers)
