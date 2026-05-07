"""集成测试：cancel + _aggregate_job_status 尊重 cancelled。

复现历史 bug：cancel 后 worker 完成 running 候选写状态触发聚合，
聚合应保持 job.status='cancelled' 而不是覆写为 succeeded/failed/running。
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


async def _new_job(client: AsyncClient, n_candidates: int = 3) -> int:
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
            json={"name": "p_cancel", "base_url": "http://e", "api_key": "sk"},
        )
    ).json()
    job = (
        await client.post(
            "/api/jobs",
            json={
                "template_code": "ref_batch",
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
async def test_cancel_marks_queued_candidates(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    job_id = await _new_job(client, n_candidates=3)
    r = await client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "cancelled"

    # 此时所有 candidate 还是 queued 状态（mock celery 没消费），cancel 应把它们改 cancelled
    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    statuses = [c["status"] for c in detail["items"][0]["candidates"]]
    assert statuses == ["cancelled"] * 3


@pytest.mark.asyncio
async def test_aggregate_keeps_cancelled_after_running_completes(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    """cancel -> 模拟 worker 完成已 running 的候选 -> _aggregate 应保持 cancelled。"""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.core.db import SessionLocal
    from app.core.settings import get_settings
    from app.models.job import JobCandidate
    from app.tasks.generate import _aggregate_job_status as agg

    job_id = await _new_job(client, n_candidates=3)

    # 把候选状态调为 [running, queued, queued]，模拟 worker 已 pickup 1 个
    async with SessionLocal() as sess:
        cs = (
            await sess.execute(
                select(JobCandidate)
                .where(JobCandidate.job_id == job_id)
                .order_by(JobCandidate.index)
            )
        ).scalars().all()
        cs[0].status = "running"
        await sess.commit()

    # 用户 cancel
    r = await client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    # 此时候选应当是 [running, cancelled, cancelled]
    async with SessionLocal() as sess:
        cs = (
            await sess.execute(
                select(JobCandidate)
                .where(JobCandidate.job_id == job_id)
                .order_by(JobCandidate.index)
            )
        ).scalars().all()
        assert [c.status for c in cs] == ["running", "cancelled", "cancelled"]

    # 模拟 worker 把 running 的候选改成 failed（dlapi 不通的现实场景），并触发 _aggregate
    # _aggregate 是同步函数，用同步 session
    s = get_settings()
    sync_url = f"sqlite:///{s.db_path.resolve().as_posix()}"
    SyncSession = sessionmaker(bind=create_engine(sync_url, future=True))
    with SyncSession() as sync_sess:
        cand = sync_sess.execute(
            select(JobCandidate).where(JobCandidate.job_id == job_id, JobCandidate.index == 1)
        ).scalar_one()
        cand.status = "failed"
        cand.last_error = "ConnectError"
        sync_sess.commit()
        agg(sync_sess, job_id)

    # 关键断言：job.status 仍是 cancelled，不应被聚合覆写
    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    assert detail["status"] == "cancelled", (
        f"expected status=cancelled, got {detail['status']}"
    )
    # 但 failed_count 已经被聚合更新（让 UI 知道取消前已完成多少）
    assert detail["failed_count"] == 1


@pytest.mark.asyncio
async def test_aggregate_all_cancelled_no_progress(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    """全部候选 cancelled 且无 succeeded/failed 时，新 _aggregate 仍判为 cancelled
    （进入此分支的前提：job.status 已是 cancelled，所以上面早返回；本 case 反向校验
    我们不会把 [cancelled, cancelled] + status=running 的 job 错判成 succeeded）"""
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import sessionmaker

    from app.core.db import SessionLocal
    from app.core.settings import get_settings
    from app.models.job import Job, JobCandidate
    from app.tasks.generate import _aggregate_job_status as agg

    job_id = await _new_job(client, n_candidates=2)
    async with SessionLocal() as sess:
        # 模拟一种边界：候选都 cancelled，但 job.status 还是 running（脏状态）
        await sess.execute(
            update(JobCandidate)
            .where(JobCandidate.job_id == job_id)
            .values(status="cancelled")
        )
        job = await sess.get(Job, job_id)
        assert job is not None
        job.status = "running"
        await sess.commit()

    s = get_settings()
    sync_url = f"sqlite:///{s.db_path.resolve().as_posix()}"
    SyncSession = sessionmaker(bind=create_engine(sync_url, future=True))
    with SyncSession() as sync_sess:
        agg(sync_sess, job_id)

    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    # 全 cancelled + 没有 succeeded/failed -> cancelled 终态
    assert detail["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_404(client: AsyncClient) -> None:
    r = await client.post("/api/jobs/9999/cancel")
    assert r.status_code == 404
