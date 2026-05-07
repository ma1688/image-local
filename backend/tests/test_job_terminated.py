"""Job 进入终态时应额外发出一个 ``job.terminated`` 事件。

设计意图（详见 vite/SSE 卡死调查）：
- ``_aggregate_job_status`` 在每次聚合后，若 job 终态为 succeeded/failed/cancelled，
  会在 ``job.updated`` 之后再 publish 一次 ``job.terminated``。
- ``POST /api/jobs/{id}/cancel`` 处理完即把 job 标为 cancelled，
  也额外 publish 一次 ``job.terminated``（worker 后续聚合可能再发一遍，前端幂等）。
- 若 job 仍在 running，不应误发 ``job.terminated``。
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
    """避免测试触发真实 Celery enqueue。

    依赖 ``client`` fixture，确保它先完成 ``app.*`` 模块的 reload，
    再在 reload 后的模块对象上 patch。
    """
    from app.services import job_runner

    sent: list[int] = []
    monkeypatch.setattr(job_runner, "_enqueue_candidate", lambda cid: sent.append(cid))
    return sent


@pytest.fixture
def _capture_emits(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> list[dict[str, Any]]:
    """拦截两个 publish_event 入口，收集所有事件 payload。

    依赖 ``client`` fixture：``client`` 每个测试都会清空 ``app.*`` 模块缓存
    并重 import；本 fixture 必须在 ``client`` 之后执行，否则 patch 的旧模块
    对象会因为 reload 而失效。
    """
    captured: list[dict[str, Any]] = []

    def _fake_publish(_job_id: int, payload: dict[str, Any], **_kwargs: Any) -> str:
        captured.append(dict(payload))
        return "0-0"

    from app.api import jobs as jobs_mod
    from app.tasks import generate as generate_mod

    monkeypatch.setattr(jobs_mod, "publish_event", _fake_publish)
    monkeypatch.setattr(generate_mod, "publish_event", _fake_publish)
    return captured


async def _new_job(client: AsyncClient, n_candidates: int = 2) -> int:
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
            json={"name": "p_term", "base_url": "http://e", "api_key": "sk"},
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


def _events_of(captured: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [e for e in captured if e.get("event") == kind]


@pytest.mark.asyncio
async def test_aggregate_emits_terminated_on_all_succeeded(
    _mock_celery: list[int],
    _capture_emits: list[dict[str, Any]],
    client: AsyncClient,
) -> None:
    """所有候选 succeeded -> 终态 succeeded -> 应发 1 条 job.terminated。"""
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import sessionmaker

    from app.core.settings import get_settings
    from app.models.job import JobCandidate
    from app.tasks.generate import _aggregate_job_status as agg

    job_id = await _new_job(client, n_candidates=2)
    _capture_emits.clear()  # 丢弃 job 创建过程中的事件，只看本次聚合

    s = get_settings()
    sync_url = f"sqlite:///{s.db_path.resolve().as_posix()}"
    SyncSession = sessionmaker(bind=create_engine(sync_url, future=True))
    with SyncSession() as sync_sess:
        sync_sess.execute(
            update(JobCandidate)
            .where(JobCandidate.job_id == job_id)
            .values(status="succeeded", output_path="x.png")
        )
        sync_sess.commit()
        agg(sync_sess, job_id)

    updated = _events_of(_capture_emits, "job.updated")
    terminated = _events_of(_capture_emits, "job.terminated")
    assert len(updated) == 1, f"expected 1 job.updated, got {updated}"
    assert len(terminated) == 1, f"expected 1 job.terminated, got {terminated}"
    assert terminated[0]["status"] == "succeeded"
    assert terminated[0]["job_id"] == job_id
    assert terminated[0]["succeeded"] == 2
    assert terminated[0]["failed"] == 0


@pytest.mark.asyncio
async def test_aggregate_emits_terminated_on_all_failed(
    _mock_celery: list[int],
    _capture_emits: list[dict[str, Any]],
    client: AsyncClient,
) -> None:
    """所有候选 failed -> 终态 failed -> 应发 job.terminated。"""
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import sessionmaker

    from app.core.settings import get_settings
    from app.models.job import JobCandidate
    from app.tasks.generate import _aggregate_job_status as agg

    job_id = await _new_job(client, n_candidates=2)
    _capture_emits.clear()

    s = get_settings()
    sync_url = f"sqlite:///{s.db_path.resolve().as_posix()}"
    SyncSession = sessionmaker(bind=create_engine(sync_url, future=True))
    with SyncSession() as sync_sess:
        sync_sess.execute(
            update(JobCandidate)
            .where(JobCandidate.job_id == job_id)
            .values(status="failed", last_error="boom")
        )
        sync_sess.commit()
        agg(sync_sess, job_id)

    terminated = _events_of(_capture_emits, "job.terminated")
    assert len(terminated) == 1
    assert terminated[0]["status"] == "failed"
    assert terminated[0]["failed"] == 2


@pytest.mark.asyncio
async def test_aggregate_does_not_emit_terminated_when_running(
    _mock_celery: list[int],
    _capture_emits: list[dict[str, Any]],
    client: AsyncClient,
) -> None:
    """有候选仍 running/queued -> 终态 running -> 不应发 job.terminated。"""
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import sessionmaker

    from app.core.settings import get_settings
    from app.models.job import JobCandidate
    from app.tasks.generate import _aggregate_job_status as agg

    job_id = await _new_job(client, n_candidates=2)
    _capture_emits.clear()

    s = get_settings()
    sync_url = f"sqlite:///{s.db_path.resolve().as_posix()}"
    SyncSession = sessionmaker(bind=create_engine(sync_url, future=True))
    with SyncSession() as sync_sess:
        # 一成一余 -> 还有 queued -> 终态 running
        cand_ids = [
            row[0]
            for row in sync_sess.execute(
                JobCandidate.__table__.select()
                .where(JobCandidate.job_id == job_id)
                .with_only_columns(JobCandidate.id)
                .order_by(JobCandidate.id)
            ).all()
        ]
        sync_sess.execute(
            update(JobCandidate)
            .where(JobCandidate.id == cand_ids[0])
            .values(status="succeeded", output_path="x.png")
        )
        sync_sess.commit()
        agg(sync_sess, job_id)

    updated = _events_of(_capture_emits, "job.updated")
    terminated = _events_of(_capture_emits, "job.terminated")
    assert updated and updated[-1]["status"] == "running"
    assert terminated == [], f"unexpected job.terminated emitted: {terminated}"


@pytest.mark.asyncio
async def test_cancel_endpoint_emits_terminated(
    _mock_celery: list[int],
    _capture_emits: list[dict[str, Any]],
    client: AsyncClient,
) -> None:
    """POST /api/jobs/{id}/cancel 应在 job.updated 之后再发一条 job.terminated。"""
    job_id = await _new_job(client, n_candidates=3)
    _capture_emits.clear()

    r = await client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    updated = _events_of(_capture_emits, "job.updated")
    terminated = _events_of(_capture_emits, "job.terminated")
    assert len(updated) == 1
    assert updated[0]["status"] == "cancelled"
    assert len(terminated) == 1
    assert terminated[0]["status"] == "cancelled"
    assert terminated[0]["job_id"] == job_id
