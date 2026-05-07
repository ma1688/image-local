"""路径校验、扫描、缩略图缓存。

设计要点（参见方案 8.1 节）：
- 所有外部传入路径都先 ``Path.resolve(strict=False)``，再判断是否落入允许根集合。
- 缩略图按 ``sha1(absolute_path) + mtime + size`` 缓存到 ``data/thumbs/<hash>.webp``。
- 单图大小、扫描数量上限来自 settings。
- 当 ``ALLOW_ANY_DIR_SCAN=False`` 时，扫描根集合只包含 outputs / 上传根；否则任意目录都允许，
  但仍会写审计日志。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.settings import get_settings

ALLOWED_EXTS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"})


class InvalidPathError(ValueError):
    """非法 / 越权 / 不存在的路径。"""


@dataclass(frozen=True)
class ImageInfo:
    path: str
    name: str
    size_bytes: int
    width: int | None
    height: int | None
    thumb_url: str
    valid: bool
    reason: str | None = None


def _settings():  # 简化引用
    return get_settings()


def allowed_roots() -> list[Path]:
    """返回当前运行下被信任的根目录（resolve 之后的绝对路径）。"""
    s = _settings()
    roots: list[Path] = []
    for p in (s.outputs_dir, s.thumbs_dir, s.APP_DATA_DIR / "uploads"):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        roots.append(p.resolve())
    return roots


def _is_within_roots(path: Path, roots: list[Path]) -> bool:
    try:
        rp = path.resolve()
    except OSError:
        return False
    return any(rp == root or root in rp.parents for root in roots)


def safe_resolve(raw: str, *, must_exist: bool = False) -> Path:
    """把外部传入的字符串路径 resolve 成绝对 Path。

    - ``ALLOW_ANY_DIR_SCAN=False`` 时强制白名单校验；越权时抛 ``InvalidPathError``。
    - ``ALLOW_ANY_DIR_SCAN=True`` 时不做白名单（仅写审计日志）。
    - 当 ``must_exist=True`` 时，路径不存在抛 ``InvalidPathError``。
    """
    if not raw or not raw.strip():
        raise InvalidPathError("path is empty")
    p = Path(raw).expanduser()
    try:
        rp = p.resolve(strict=False)
    except OSError as exc:
        raise InvalidPathError(f"cannot resolve path: {exc}") from exc

    if must_exist and not rp.exists():
        raise InvalidPathError(f"path not found: {rp.as_posix()}")

    s = _settings()
    if not s.ALLOW_ANY_DIR_SCAN:
        roots = allowed_roots()
        if not _is_within_roots(rp, roots):
            raise InvalidPathError(
                f"path outside allowed roots: {rp.as_posix()}"
            )
    else:
        logger.info("[audit] external path access: {}", rp.as_posix())
    return rp


def safe_resolve_under(raw: str, root: Path) -> Path:
    """强制 raw resolve 后必须落在 root 下；用于 /api/files 文件下载防穿越。"""
    if not raw or not raw.strip():
        raise InvalidPathError("path is empty")
    p = (root / raw).resolve(strict=False) if not Path(raw).is_absolute() else Path(raw).resolve(
        strict=False
    )
    root_resolved = root.resolve()
    try:
        p.relative_to(root_resolved)
    except ValueError as exc:
        raise InvalidPathError(
            f"path outside allowed root: {p.as_posix()} not under {root_resolved.as_posix()}"
        ) from exc
    return p


def _thumb_key(path: Path) -> str:
    try:
        st = path.stat()
    except OSError:
        return hashlib.sha1(path.as_posix().encode("utf-8")).hexdigest()
    payload = f"{path.as_posix()}|{st.st_mtime_ns}|{st.st_size}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def thumb_url_of(path: Path) -> str:
    """根据源文件计算缩略图 URL（相对前端 base，由前端 fetch GET /api/files?path=...）"""
    s = _settings()
    return f"/api/files?path={(s.thumbs_dir / (_thumb_key(path) + '.webp')).as_posix()}"


def ensure_thumbnail(path: Path, *, max_side: int = 256) -> Path | None:
    """生成（或复用）缩略图；失败返回 None。"""
    s = _settings()
    cache = s.thumbs_dir / (_thumb_key(path) + ".webp")
    if cache.exists() and cache.stat().st_size > 0:
        return cache
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((max_side, max_side))
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(".webp.tmp")
            im.save(tmp, format="WEBP", quality=80, method=4)
            os.replace(tmp, cache)
            return cache
    except (OSError, UnidentifiedImageError) as exc:
        logger.warning("thumbnail failed for {}: {}", path.as_posix(), exc)
        return None


def _read_image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(path) as im:
            return im.size  # (w, h)
    except (OSError, UnidentifiedImageError):
        return None, None


def scan_directory(
    raw_dir: str, *, recursive: bool = False
) -> tuple[list[ImageInfo], int, bool]:
    """扫描目录，返回 (images, total_seen, truncated)。

    - 仅扫描 ALLOWED_EXTS。
    - 单图 > settings.SOURCE_IMAGE_MAX_BYTES 标记 invalid 但仍保留在列表里（UI 提示）。
    - 数量超过 settings.SCAN_FILE_LIMIT 时截断并返回 truncated=True。
    """
    root = safe_resolve(raw_dir, must_exist=True)
    if not root.is_dir():
        raise InvalidPathError(f"not a directory: {root.as_posix()}")

    s = _settings()
    out: list[ImageInfo] = []
    total = 0
    truncated = False

    iterator = root.rglob("*") if recursive else root.iterdir()
    for entry in iterator:
        try:
            if entry.is_symlink():
                continue
            if not entry.is_file():
                continue
        except OSError:
            continue
        if entry.suffix.lower() not in ALLOWED_EXTS:
            continue
        total += 1
        if len(out) >= s.SCAN_FILE_LIMIT:
            truncated = True
            continue

        try:
            stat = entry.stat()
        except OSError:
            continue

        size_bytes = stat.st_size
        valid = True
        reason: str | None = None
        if size_bytes > s.SOURCE_IMAGE_MAX_BYTES:
            valid = False
            reason = f"size>{s.SOURCE_IMAGE_MAX_BYTES} bytes"

        w, h = _read_image_size(entry) if valid else (None, None)
        if valid and w is None:
            valid = False
            reason = "unrecognized image"

        if valid:
            ensure_thumbnail(entry)

        out.append(
            ImageInfo(
                path=entry.resolve().as_posix(),
                name=entry.name,
                size_bytes=size_bytes,
                width=w,
                height=h,
                thumb_url=thumb_url_of(entry) if valid else "",
                valid=valid,
                reason=reason,
            )
        )

    return out, total, truncated
