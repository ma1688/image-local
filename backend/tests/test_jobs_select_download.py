"""集成测试：PATCH select / GET download。

通过 ``SessionLocal`` 绕过 worker 直接构造 succeeded 候选 + 真实文件，
覆盖：
- 选中互斥（同 item 仅 1 个）
- 仅 succeeded 可被选中
- 取消选中
- 下载 all / selected / 空选中 / job 不存在
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image


def _png_bytes(color: tuple[int, int, int] = (200, 100, 50)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
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


async def _seed_succeeded_job(
    client: AsyncClient, items: int = 2, candidates: int = 2
) -> tuple[int, list[int], list[int]]:
    """提交一个 job 并把候选都改成 succeeded + 写真实 png 文件。

    返回 (job_id, item_ids, candidate_ids)。
    """
    files = [
        ("files", (f"x{i}.png", _png_bytes(), "image/png")) for i in range(items)
    ]
    upload = (await client.post("/api/images/upload", files=files)).json()
    paths = [it["path"] for it in upload["items"]]

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
        "prompt": "x",
        "candidates_per_image": candidates,
        "auto_retry": False,
        "retry_max": 1,
        "output_dir": "data/outputs",
        "source_paths": paths,
    }
    job_resp = await client.post("/api/jobs", json=payload)
    assert job_resp.status_code == 201, job_resp.text
    job_id = int(job_resp.json()["id"])

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.core.settings import get_settings
    from app.models.job import JobCandidate, JobItem

    s = get_settings()
    out_root = s.outputs_dir / str(job_id)

    async with SessionLocal() as sess:
        rows = (
            await sess.execute(
                select(JobItem).where(JobItem.job_id == job_id)
            )
        ).scalars().all()
        item_ids = [int(r.id) for r in rows]
        cand_ids: list[int] = []
        for it in rows:
            cs = (
                await sess.execute(
                    select(JobCandidate).where(JobCandidate.item_id == it.id)
                )
            ).scalars().all()
            for c in cs:
                target_dir = out_root / str(it.id)
                target_dir.mkdir(parents=True, exist_ok=True)
                fp = target_dir / f"cand_{int(c.index)}.png"
                fp.write_bytes(_png_bytes((50 * int(c.index) % 255, 80, 120)))
                c.status = "succeeded"
                c.output_path = fp.as_posix()
                cand_ids.append(int(c.id))
        await sess.commit()

    return job_id, item_ids, cand_ids


@pytest.mark.asyncio
async def test_select_candidate_mutual_exclusion(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    job_id, item_ids, _ = await _seed_succeeded_job(client, items=1, candidates=3)
    item_id = item_ids[0]

    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    candidates = detail["items"][0]["candidates"]
    cand_a = candidates[0]["id"]
    cand_b = candidates[1]["id"]

    r1 = await client.patch(
        f"/api/jobs/{job_id}/candidates/{cand_a}/select",
        json={"is_selected": True},
    )
    assert r1.status_code == 200
    assert r1.json()["is_selected"] is True

    r2 = await client.patch(
        f"/api/jobs/{job_id}/candidates/{cand_b}/select",
        json={"is_selected": True},
    )
    assert r2.status_code == 200
    assert r2.json()["is_selected"] is True

    detail2 = (await client.get(f"/api/jobs/{job_id}")).json()
    selected = [
        c["id"]
        for c in detail2["items"][0]["candidates"]
        if c["is_selected"]
    ]
    assert selected == [cand_b], f"expected only {cand_b} selected, got {selected}"
    assert detail2["items"][0]["id"] == item_id


@pytest.mark.asyncio
async def test_select_candidate_unselect(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    job_id, _, cand_ids = await _seed_succeeded_job(client, items=1, candidates=1)
    cid = cand_ids[0]

    await client.patch(
        f"/api/jobs/{job_id}/candidates/{cid}/select",
        json={"is_selected": True},
    )
    r = await client.patch(
        f"/api/jobs/{job_id}/candidates/{cid}/select",
        json={"is_selected": False},
    )
    assert r.status_code == 200
    assert r.json()["is_selected"] is False


@pytest.mark.asyncio
async def test_select_only_succeeded(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    """非 succeeded 候选不能被选中（应 400）。"""
    files = [("files", ("a.png", _png_bytes(), "image/png"))]
    paths = [
        it["path"]
        for it in (await client.post("/api/images/upload", files=files)).json()["items"]
    ]
    profile = (
        await client.post(
            "/api/api-profiles",
            json={"name": "p", "base_url": "http://e", "api_key": "sk"},
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
                "prompt": "",
                "candidates_per_image": 1,
                "auto_retry": False,
                "retry_max": 1,
                "output_dir": "data/outputs",
                "source_paths": paths,
            },
        )
    ).json()
    cid = job["id"]
    detail = (await client.get(f"/api/jobs/{cid}")).json()
    candidate_id = detail["items"][0]["candidates"][0]["id"]

    r = await client.patch(
        f"/api/jobs/{cid}/candidates/{candidate_id}/select",
        json={"is_selected": True},
    )
    assert r.status_code == 400
    assert "succeeded" in r.json()["detail"]


@pytest.mark.asyncio
async def test_select_candidate_404(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    r = await client.patch(
        "/api/jobs/9999/candidates/9999/select",
        json={"is_selected": True},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_download_all(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    job_id, _, cand_ids = await _seed_succeeded_job(client, items=2, candidates=2)
    r = await client.get(f"/api/jobs/{job_id}/download?scope=all")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(BytesIO(r.content))
    names = zf.namelist()
    # 2 items x 2 candidates = 4 file
    assert len(names) == len(cand_ids) == 4
    for name in names:
        assert name.startswith("x")  # 来自 source_name xN.png 的 stem
        assert "_cand_" in name
    # 校验文件内容非空
    for n in names:
        assert len(zf.read(n)) > 0


@pytest.mark.asyncio
async def test_download_selected_only(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    job_id, _, _ = await _seed_succeeded_job(client, items=2, candidates=2)
    # 只选中第一个 item 的 cand_1
    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    target = detail["items"][0]["candidates"][0]["id"]
    await client.patch(
        f"/api/jobs/{job_id}/candidates/{target}/select",
        json={"is_selected": True},
    )

    r = await client.get(f"/api/jobs/{job_id}/download?scope=selected")
    assert r.status_code == 200
    zf = zipfile.ZipFile(BytesIO(r.content))
    assert len(zf.namelist()) == 1


@pytest.mark.asyncio
async def test_download_selected_empty(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    job_id, _, _ = await _seed_succeeded_job(client, items=1, candidates=1)
    r = await client.get(f"/api/jobs/{job_id}/download?scope=selected")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_download_job_not_found(client: AsyncClient) -> None:
    r = await client.get("/api/jobs/9999/download?scope=all")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_download_invalid_scope(client: AsyncClient) -> None:
    r = await client.get("/api/jobs/1/download?scope=evil")
    assert r.status_code == 422  # Query pattern 校验


@pytest.mark.asyncio
async def test_download_skips_path_outside_data_dir(
    _mock_celery: list[int], client: AsyncClient, tmp_path: Path
) -> None:
    """候选 output_path 越权（落在 APP_DATA_DIR 之外）的文件应被忽略，不进入 zip。"""
    job_id, _, _ = await _seed_succeeded_job(client, items=1, candidates=1)

    from sqlalchemy import select, update

    from app.core.db import SessionLocal
    from app.models.job import JobCandidate

    bogus = tmp_path / "outside.png"
    bogus.write_bytes(_png_bytes())

    async with SessionLocal() as sess:
        rows = (
            await sess.execute(
                select(JobCandidate).where(JobCandidate.job_id == job_id)
            )
        ).scalars().all()
        await sess.execute(
            update(JobCandidate)
            .where(JobCandidate.id == rows[0].id)
            .values(output_path=str(bogus))
        )
        await sess.commit()

    r = await client.get(f"/api/jobs/{job_id}/download?scope=all")
    # 这个 job 只有 1 张候选，且被改成越权路径 -> zip 内 0 文件
    # 当前实现仍返回 200 + 空 zip（pairs 不为空，只是 _resolve_candidate_path 跳过）
    assert r.status_code == 200
    zf = zipfile.ZipFile(BytesIO(r.content))
    assert zf.namelist() == []
