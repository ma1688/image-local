"""worker 入口 short-circuit：当 job 已被 cancel 时，
generate_one_candidate 应直接把候选 -> cancelled，不再走真实生成逻辑。
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def _mock_celery(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> list[int]:
    from app.services import job_runner

    sent: list[int] = []

    def _stub(cid: int) -> Any:
        sent.append(cid)

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
            json={"name": "p_sc", "base_url": "http://e", "api_key": "sk"},
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


@pytest.mark.asyncio
async def test_worker_short_circuits_when_job_cancelled(
    _mock_celery: list[int], client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.db import SessionLocal
    from app.models.job import JobCandidate
    from app.tasks import generate as gen_mod

    job_id = await _new_job(client, n=2)

    # 模拟一个候选已被 worker prefetch 且置 running（worker 已开始跑）
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
        running_cid = int(cs[0].id)

    # 用户 cancel
    r = await client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    # 让 generate 真实生成路径炸掉，作为反向监督：若 short-circuit 失效会触发它
    def _boom(*a: Any, **kw: Any) -> Any:
        raise AssertionError("generate_one should not be called when job cancelled")

    monkeypatch.setattr(gen_mod, "generate_one", _boom)

    # 直接在 eager mode 调用任务（不走 broker）
    result = gen_mod.generate_one_candidate.run(running_cid)
    assert result.get("ok") is True
    assert result.get("skipped") is True

    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    assert detail["status"] == "cancelled"
    statuses = {c["status"] for c in detail["items"][0]["candidates"]}
    # 这个本来 running 的应该被 short-circuit 改成 cancelled
    assert "cancelled" in statuses
    # failed_count 不应被增加
    assert detail["failed_count"] == 0
