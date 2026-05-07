"""并发场景测试：多个 worker 进程同时完成候选时，jobs.succeeded_count /
failed_count 必须收敛到真实候选状态聚合值，不会因为 commit 顺序不可控而被
"过时"的较小值覆盖。

历史 bug：原本 _aggregate_job_status 用 ORM 流程（SELECT counts -> SET on
ORM job -> session.commit()），多 session 并发时最后 commit 的不一定基于最新
counts，会写入小于真实值的 failed_count（例如 4 个候选全 failed 但 DB 里
failed_count=1）。修复后改为单条 UPDATE + 子查询，由 SQLite 写锁保证每次
commit 都基于实时聚合。
"""

from __future__ import annotations

import threading
from io import BytesIO
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def _mock_celery(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> list[int]:
    """注意：必须依赖 client fixture，因为 client 会先 reload app.* 模块；
    否则 monkeypatch 改的是被换掉的 job_runner 模块对象，不会生效。"""
    from app.services import job_runner

    sent: list[int] = []

    def _stub(cid: int) -> Any:
        sent.append(cid)
        return None

    monkeypatch.setattr(job_runner, "_enqueue_candidate", _stub)
    return sent


async def _new_job(client: AsyncClient, n: int) -> int:
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
            json={"name": "p_race", "base_url": "http://e", "api_key": "sk"},
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
                "candidates_per_image": n,
                "auto_retry": False,
                "retry_max": 1,
                "output_dir": "data/outputs",
                "source_paths": paths,
            },
        )
    ).json()
    return int(job["id"])


def _sync_session_factory() -> sessionmaker:
    from app.core.settings import get_settings

    s = get_settings()
    sync_url = f"sqlite:///{s.db_path.resolve().as_posix()}"
    eng = create_engine(
        sync_url,
        future=True,
        connect_args={"timeout": 10, "check_same_thread": False},
    )
    return sessionmaker(bind=eng, expire_on_commit=False)


def _worker_finish(cand_id: int, job_id: int, final_status: str) -> None:
    """模拟 worker 进程完成一个候选：写 cand.status -> _aggregate_job_status。

    每个线程都用独立 session（独立 connection），与生产 worker 多进程语义对齐。
    """
    from app.models.job import JobCandidate
    from app.tasks.generate import _aggregate_job_status as agg

    SyncSession = _sync_session_factory()
    with SyncSession() as sess:
        cand = sess.execute(
            select(JobCandidate).where(JobCandidate.id == cand_id)
        ).scalar_one()
        cand.status = final_status
        if final_status == "failed":
            cand.last_error = "ConnectError: simulated"
        sess.commit()
        agg(sess, job_id)


@pytest.mark.asyncio
async def test_concurrent_finishes_all_failed(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    """4 候选并发完成都 failed -> failed_count 必须为 4，不能被 race 写小。"""
    from app.core.db import SessionLocal
    from app.models.job import JobCandidate

    job_id = await _new_job(client, n=4)
    async with SessionLocal() as sess:
        cs = (
            await sess.execute(
                select(JobCandidate)
                .where(JobCandidate.job_id == job_id)
                .order_by(JobCandidate.index)
            )
        ).scalars().all()
        for c in cs:
            c.status = "running"
        await sess.commit()
        cand_ids = [int(c.id) for c in cs]

    barrier = threading.Barrier(len(cand_ids))

    def _go(cid: int) -> None:
        barrier.wait()  # 让所有线程尽可能同时进入临界区
        _worker_finish(cid, job_id, "failed")

    threads = [threading.Thread(target=_go, args=(cid,)) for cid in cand_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads)

    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    assert detail["failed_count"] == 4, detail
    assert detail["succeeded_count"] == 0
    assert detail["status"] == "failed"


@pytest.mark.asyncio
async def test_concurrent_finishes_mixed(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    """3 succeeded + 2 failed 并发完成 -> counts 必须分别是 3 / 2，status=failed。"""
    from app.core.db import SessionLocal
    from app.models.job import JobCandidate

    job_id = await _new_job(client, n=5)
    async with SessionLocal() as sess:
        cs = (
            await sess.execute(
                select(JobCandidate)
                .where(JobCandidate.job_id == job_id)
                .order_by(JobCandidate.index)
            )
        ).scalars().all()
        for c in cs:
            c.status = "running"
        await sess.commit()
        cand_ids = [int(c.id) for c in cs]

    targets = ["succeeded", "succeeded", "succeeded", "failed", "failed"]
    barrier = threading.Barrier(len(cand_ids))

    def _go(cid: int, target: str) -> None:
        barrier.wait()
        _worker_finish(cid, job_id, target)

    threads = [
        threading.Thread(target=_go, args=(cid, t))
        for cid, t in zip(cand_ids, targets, strict=True)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    assert detail["succeeded_count"] == 3, detail
    assert detail["failed_count"] == 2, detail
    assert detail["status"] == "failed"


@pytest.mark.asyncio
async def test_concurrent_with_cancel_in_between(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    """cancel + 多个 in-flight 候选并发 failed -> status 仍为 cancelled，
    failed_count 等于实际 failed 候选数。"""
    from app.core.db import SessionLocal
    from app.models.job import JobCandidate

    job_id = await _new_job(client, n=4)
    # 全部置 running，模拟 worker 全部 prefetch 进行中
    async with SessionLocal() as sess:
        cs = (
            await sess.execute(
                select(JobCandidate)
                .where(JobCandidate.job_id == job_id)
                .order_by(JobCandidate.index)
            )
        ).scalars().all()
        for c in cs:
            c.status = "running"
        await sess.commit()
        cand_ids = [int(c.id) for c in cs]

    # 用户在 worker 完成前 cancel
    r = await client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    # 4 个 worker 并发完成（都 failed，模拟 dlapi 不通）
    barrier = threading.Barrier(len(cand_ids))

    def _go(cid: int) -> None:
        barrier.wait()
        _worker_finish(cid, job_id, "failed")

    threads = [threading.Thread(target=_go, args=(cid,)) for cid in cand_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    assert detail["status"] == "cancelled", detail
    assert detail["failed_count"] == 4, detail
