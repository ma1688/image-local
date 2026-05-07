"""集成测试：POST /api/jobs / GET /api/jobs/{id}。

Celery 的 ``.delay()`` 在测试中被 mock 掉，避免 worker 真实跑。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (16, 16)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def _mock_celery(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """在 client fixture 已 reload 模块后，再 patch 入队函数。"""
    from app.services import job_runner

    sent: list[int] = []

    def _stub(cid: int) -> Any:
        sent.append(cid)
        return None

    monkeypatch.setattr(job_runner, "_enqueue_candidate", _stub)
    return sent


@pytest.mark.asyncio
async def test_create_job_happy_path(
    _mock_celery: list[int], client: AsyncClient, tmp_path: Path
) -> None:
    # 上传 2 张参考图（在容器视角下 /api/images/upload 后落地于 data/uploads/）
    files = [
        ("files", ("a.png", _png_bytes(), "image/png")),
        ("files", ("b.png", _png_bytes(), "image/png")),
    ]
    upload = (await client.post("/api/images/upload", files=files)).json()
    paths = [it["path"] for it in upload["items"]]

    # 先创建一个 api profile
    profile = (
        await client.post(
            "/api/api-profiles",
            json={
                "name": "p",
                "base_url": "http://example.test",
                "api_key": "sk-test",
            },
        )
    ).json()

    payload = {
        "template_code": "ref_batch",
        "api_profile_id": profile["id"],
        "model": "gpt-image-2",
        "size": "1024x1024",
        "prompt": "hello",
        "candidates_per_image": 3,
        "auto_retry": True,
        "retry_max": 2,
        "output_dir": "data/outputs",
        "source_paths": paths,
    }
    resp = await client.post("/api/jobs", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["total_candidates"] == 6  # 2 imgs * 3 candidates
    assert body["candidates_per_image"] == 3

    # Celery delay 被调用了 6 次，每次传一个 candidate_id
    assert len(_mock_celery) == 6
    assert all(isinstance(c, int) and c > 0 for c in _mock_celery)

    # GET /api/jobs/{id} 应返回 items + candidates
    detail = (await client.get(f"/api/jobs/{body['id']}")).json()
    assert len(detail["items"]) == 2
    for it in detail["items"]:
        assert len(it["candidates"]) == 3
        for c in it["candidates"]:
            assert c["status"] == "queued"
            assert c["attempts"] == 0


@pytest.mark.asyncio
async def test_create_job_invalid_path(client: AsyncClient, tmp_path: Path) -> None:
    profile = (
        await client.post(
            "/api/api-profiles",
            json={
                "name": "p",
                "base_url": "http://example.test",
                "api_key": "sk-test",
            },
        )
    ).json()

    resp = await client.post(
        "/api/jobs",
        json={
            "template_code": "ref_batch",
            "api_profile_id": profile["id"],
            "model": "m",
            "size": "1024x1024",
            "prompt": "",
            "candidates_per_image": 1,
            "auto_retry": False,
            "retry_max": 1,
            "output_dir": "data/outputs",
            "source_paths": [str(tmp_path / "no-such.png")],
        },
    )
    assert resp.status_code == 400
    assert "invalid source path" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_job_not_found(client: AsyncClient) -> None:
    r = await client.get("/api/jobs/9999")
    assert r.status_code == 404
