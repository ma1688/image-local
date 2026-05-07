"""prompt 模板占位符解析与创建任务时的校验。"""

from __future__ import annotations

from io import BytesIO

import pytest
from httpx import AsyncClient
from PIL import Image

from app.services.prompt_template import (
    KNOWN_VARS,
    extract_placeholders,
    validate_prompt,
)


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    return buf.getvalue()


def test_extract_placeholders_basic() -> None:
    assert extract_placeholders("") == []
    assert extract_placeholders("hello world") == []
    assert extract_placeholders("hi {prompt}") == ["prompt"]
    # 重复变量去重，保留首次顺序
    assert extract_placeholders("{a} {b} {a}") == ["a", "b"]
    # 双花括号转义不当变量处理
    assert extract_placeholders("{{escaped}} {prompt}") == ["prompt"]


def test_validate_prompt_requires_user() -> None:
    pv = validate_prompt("hi {prompt}", "")
    assert pv.placeholders == ["prompt"]
    assert pv.unknown == []
    assert pv.requires_user_prompt is True


def test_validate_prompt_unknown_var() -> None:
    pv = validate_prompt("hi {prompt} seed={seed}", "world")
    assert pv.placeholders == ["prompt", "seed"]
    assert pv.unknown == ["seed"]
    assert pv.requires_user_prompt is False


def test_known_vars_only_prompt_for_now() -> None:
    assert KNOWN_VARS == {"prompt"}


@pytest.fixture
def _mock_celery(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> list[int]:
    from app.services import job_runner

    sent: list[int] = []
    monkeypatch.setattr(job_runner, "_enqueue_candidate", lambda c: sent.append(c))
    return sent


async def _seed_template(client: AsyncClient, code: str, prompt_template: str) -> None:
    r = await client.post(
        "/api/templates",
        json={
            "code": code,
            "name": code,
            "prompt_template": prompt_template,
        },
    )
    assert r.status_code in (200, 201), r.text


async def _upload(client: AsyncClient) -> str:
    files = [("files", ("a.png", _png(), "image/png"))]
    return (
        await client.post("/api/images/upload", files=files)
    ).json()["items"][0]["path"]


async def _profile_id(client: AsyncClient) -> int:
    return (
        await client.post(
            "/api/api-profiles",
            json={"name": "p_pt", "base_url": "http://e", "api_key": "sk"},
        )
    ).json()["id"]


@pytest.mark.asyncio
async def test_template_list_exposes_placeholders(client: AsyncClient) -> None:
    await _seed_template(client, "tpl_pholder", "draw {prompt} with {seed}")
    r = await client.get("/api/templates")
    assert r.status_code == 200
    items = r.json()
    one = next(i for i in items if i["code"] == "tpl_pholder")
    assert one["placeholders"] == ["prompt", "seed"]
    assert one["unknown_placeholders"] == ["seed"]


@pytest.mark.asyncio
async def test_create_job_blocked_when_prompt_required(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    await _seed_template(client, "tpl_need_prompt", "depict {prompt}")
    src = await _upload(client)
    pid = await _profile_id(client)
    r = await client.post(
        "/api/jobs",
        json={
            "template_code": "tpl_need_prompt",
            "api_profile_id": pid,
            "model": "m",
            "size": "1024x1024",
            "prompt": "",
            "candidates_per_image": 1,
            "auto_retry": False,
            "retry_max": 1,
            "output_dir": "data/outputs",
            "source_paths": [src],
        },
    )
    assert r.status_code == 400
    assert "prompt" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_job_blocked_on_unknown_placeholder(
    _mock_celery: list[int], client: AsyncClient
) -> None:
    await _seed_template(client, "tpl_seed_var", "draw {prompt} seed={seed}")
    src = await _upload(client)
    pid = await _profile_id(client)
    r = await client.post(
        "/api/jobs",
        json={
            "template_code": "tpl_seed_var",
            "api_profile_id": pid,
            "model": "m",
            "size": "1024x1024",
            "prompt": "world",
            "candidates_per_image": 1,
            "auto_retry": False,
            "retry_max": 1,
            "output_dir": "data/outputs",
            "source_paths": [src],
        },
    )
    assert r.status_code == 400
    assert "seed" in r.json()["detail"]
