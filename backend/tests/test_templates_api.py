"""模板 API 的 happy path + 唯一性约束错误分支。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_builtin_templates(client: AsyncClient) -> None:
    resp = await client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    codes = {t["code"] for t in data}
    assert {"ref_batch", "product_style", "gift_box", "custom"} <= codes
    for t in data:
        if t["code"] in {"ref_batch", "product_style", "gift_box", "custom"}:
            assert t["builtin"] is True


@pytest.mark.asyncio
async def test_create_custom_template(client: AsyncClient) -> None:
    payload = {
        "code": "my_custom",
        "name": "我的模板",
        "prompt_template": "测试 {prompt}",
        "default_size": "1024x1024",
    }
    resp = await client.post("/api/templates", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "my_custom"
    assert body["builtin"] is False


@pytest.mark.asyncio
async def test_create_template_conflict(client: AsyncClient) -> None:
    payload = {"code": "ref_batch", "name": "重复模板", "prompt_template": ""}
    resp = await client.post("/api/templates", json=payload)
    assert resp.status_code == 409
