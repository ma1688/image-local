"""POST /api/images/scan & /upload 的集成测试。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image


def _png_bytes(size: tuple[int, int] = (16, 16), color: str = "red") -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _alembic_ini_path() -> str:
    return (Path(__file__).resolve().parents[1] / "alembic.ini").as_posix()


@pytest.mark.asyncio
async def test_scan_endpoint(client: AsyncClient, tmp_path: Path) -> None:
    img1 = tmp_path / "a.png"
    img1.write_bytes(_png_bytes())
    img2 = tmp_path / "b.jpg"
    Image.new("RGB", (16, 16)).save(img2, format="JPEG")
    (tmp_path / "ignore.txt").write_text("nope")

    resp = await client.post("/api/images/scan", json={"dir": str(tmp_path)})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_seen"] == 2
    assert {it["name"] for it in data["items"]} == {"a.png", "b.jpg"}
    for it in data["items"]:
        assert it["valid"] is True
        assert it["thumb_url"].startswith("/api/files?path=")


@pytest.mark.asyncio
async def test_scan_invalid_path(client: AsyncClient, tmp_path: Path) -> None:
    resp = await client.post(
        "/api/images/scan", json={"dir": str(tmp_path / "does-not-exist")}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_scan_not_a_dir(client: AsyncClient, tmp_path: Path) -> None:
    f = tmp_path / "single.png"
    f.write_bytes(_png_bytes())
    resp = await client.post("/api/images/scan", json={"dir": str(f)})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_endpoint(client: AsyncClient) -> None:
    files = [
        ("files", ("foo.png", _png_bytes(), "image/png")),
        ("files", ("bar.jpg", _png_bytes(color="blue"), "image/jpeg")),
        ("files", ("ignore.txt", b"hi", "text/plain")),
    ]
    resp = await client.post("/api/images/upload", files=files)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert len(data["items"]) == 2  # ignore.txt 被跳过
    assert {it["name"] for it in data["items"]} == {"foo.png", "bar.jpg"}
    assert data["upload_dir"]


@pytest.mark.asyncio
async def test_files_endpoint_404_outside_roots(client: AsyncClient, tmp_path: Path) -> None:
    """ALLOW_ANY_DIR_SCAN 默认 true，因此外部文件可访问，但不存在就 404。"""
    fake = tmp_path / "ghost.png"
    resp = await client.get(f"/api/files?path={fake.as_posix()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_files_endpoint_rejects_traversal(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """关闭 ALLOW_ANY_DIR_SCAN 后，越权访问应当 403。"""
    from app.core import settings as settings_mod

    monkeypatch.setenv("ALLOW_ANY_DIR_SCAN", "false")
    settings_mod.get_settings.cache_clear()

    # 一个肯定存在但不在 data 根下的文件：alembic.ini（同步路径计算，避免 pathlib 异步告警）
    target = _alembic_ini_path()
    resp = await client.get(f"/api/files?path={target}")
    assert resp.status_code == 403, resp.text

    settings_mod.get_settings.cache_clear()
