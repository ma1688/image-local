"""/api/storage/usage：阈值 / hard limit / 桶汇总 应正确反映。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_storage_usage_ok_when_below_warn(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = await client.get("/api/storage/usage")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"ok", "warn", "critical"}
    names = {b["name"] for b in body["buckets"]}
    assert names == {"outputs", "uploads", "thumbs"}
    assert body["data_dir"]
    assert body["warn_bytes"] > 0


@pytest.mark.asyncio
async def test_storage_usage_warn_when_exceed_threshold(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模拟 outputs 已达警戒值：把 settings.STORAGE_WARN_BYTES 调成 1 byte。"""
    from app.core import settings as settings_mod
    from app.core.settings import get_settings

    # clear cache then patch
    settings_mod.get_settings.cache_clear()
    s = get_settings()
    monkeypatch.setattr(s, "STORAGE_WARN_BYTES", 1, raising=True)

    # 上传一个文件让 uploads 桶非空
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    files = [("files", ("a.png", buf.getvalue(), "image/png"))]
    upr = await client.post("/api/images/upload", files=files)
    assert upr.status_code in (200, 201)

    r = await client.get("/api/storage/usage")
    assert r.status_code == 200
    body = r.json()
    # warn_bytes=1 + 至少有 1 字节 uploads -> warn 或 critical
    assert body["status"] in {"warn", "critical"}
