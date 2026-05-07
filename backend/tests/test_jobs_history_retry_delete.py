"""集成测试：GET /api/jobs 分页过滤 / POST retry-failed / DELETE。

依赖现有 _mock_celery 风格，但每个 case 自己 patch。
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def _mock_celery(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    from app.services import job_runner

    sent: list[int] = []

    def _stub(cid: int) -> Any:
        sent.append(cid)
        return None

    monkeypatch.setattr(job_runner, "_enqueue_candidate", _stub)
    return sent


async def _create_job(
    client: AsyncClient, template: str = "ref_batch", n_candidates: int = 1
) -> int:
    files = [("files", ("a.png", _png(), "image/png"))]
    paths = [
        it["path"]
        for it in (
            await client.post("/api/images/upload", files=files)
        ).json()["items"]
    ]
    profile = (
        await client.post(
            "/api/api-profiles",
            json={
                "name": f"p_{template}",
                "base_url": "http://e",
                "api_key": "sk",
            },
        )
    ).json()
    job = (
        await client.post(
            "/api/jobs",
            json={
                "template_code": template,
                "api_profile_id": profile["id"],
                "model": "m",
                "size": "1024x1024",
                "prompt": "x",
                "candidates_per_image": n_candidates,
                "auto_retry": False,
                "retry_max": 1,
                "output_dir": "data/outputs",
                "source_paths": paths,
            },
        )
    ).json()
    return int(job["id"])


@pytest.mark.asyncio
async def test_list_jobs_pagination(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    """用独特 template_code 隔离不同测试创建的 job，避免会话级 DB 污染。"""
    tpl = "pagination_only_test"
    ids = []
    for _ in range(3):
        ids.append(await _create_job(client, template=tpl))

    page1 = (
        await client.get(f"/api/jobs?template_code={tpl}&limit=2&offset=0")
    ).json()
    assert page1["total"] == 3
    assert page1["limit"] == 2
    assert page1["offset"] == 0
    assert len(page1["items"]) == 2

    page2 = (
        await client.get(f"/api/jobs?template_code={tpl}&limit=2&offset=2")
    ).json()
    assert len(page2["items"]) == 1
    assert page2["items"][0]["id"] == ids[0]  # 最旧的


@pytest.mark.asyncio
async def test_list_jobs_filter_by_template(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    a = await _create_job(client, template="ref_batch")
    b = await _create_job(client, template="custom_flow")

    r_a = (
        await client.get("/api/jobs?template_code=ref_batch")
    ).json()
    ids_a = [it["id"] for it in r_a["items"]]
    assert a in ids_a and b not in ids_a

    r_b = (
        await client.get("/api/jobs?template_code=custom_flow")
    ).json()
    ids_b = [it["id"] for it in r_b["items"]]
    assert b in ids_b and a not in ids_b


@pytest.mark.asyncio
async def test_retry_failed_resets_and_redispatches(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    job_id = await _create_job(client, n_candidates=2)

    # 把候选标记为 1 个 failed + 1 个 succeeded
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.job import Job, JobCandidate

    async with SessionLocal() as sess:
        cs = (
            await sess.execute(
                select(JobCandidate).where(JobCandidate.job_id == job_id)
            )
        ).scalars().all()
        cs[0].status = "failed"
        cs[0].last_error = "boom"
        cs[0].attempts = 2
        cs[1].status = "succeeded"
        cs[1].output_path = "/tmp/ok.png"
        job = await sess.get(Job, job_id)
        assert job is not None
        job.status = "failed"
        job.failed_count = 1
        job.succeeded_count = 1
        await sess.commit()

    _mock_celery.clear()
    r = await client.post(f"/api/jobs/{job_id}/retry-failed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["failed_count"] == 0
    # 仅 failed 那 1 个被重新派发
    assert _mock_celery == [int(cs[0].id)]

    # 校验：DB 中 failed 候选已 reset，succeeded 保留
    async with SessionLocal() as sess:
        rows = (
            await sess.execute(
                select(JobCandidate).where(JobCandidate.job_id == job_id)
            )
        ).scalars().all()
        rows.sort(key=lambda x: int(x.index))
        assert rows[0].status == "queued"
        assert rows[0].attempts == 0
        assert rows[0].last_error is None
        assert rows[1].status == "succeeded"
        assert rows[1].output_path == "/tmp/ok.png"


@pytest.mark.asyncio
async def test_retry_failed_no_failed_400(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    job_id = await _create_job(client)
    r = await client.post(f"/api/jobs/{job_id}/retry-failed")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_job_running_blocked(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    job_id = await _create_job(client)
    r = await client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_delete_job_with_files(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    job_id = await _create_job(client)

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.core.settings import get_settings
    from app.models.job import Job, JobCandidate

    s = get_settings()
    out_dir = s.outputs_dir / str(job_id) / "1"
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = out_dir / "cand_1.png"
    fp.write_bytes(_png())

    # 设为 succeeded 才能删
    async with SessionLocal() as sess:
        job = await sess.get(Job, job_id)
        assert job is not None
        job.status = "succeeded"
        await sess.commit()

    r = await client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 204
    assert not fp.exists()
    assert not (s.outputs_dir / str(job_id)).exists()

    # DB 里 cascade 删除
    async with SessionLocal() as sess:
        cs = (
            await sess.execute(
                select(JobCandidate).where(JobCandidate.job_id == job_id)
            )
        ).scalars().all()
        assert cs == []


@pytest.mark.asyncio
async def test_delete_job_404(client: AsyncClient) -> None:
    r = await client.delete("/api/jobs/9999")
    assert r.status_code == 404
