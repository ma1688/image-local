"""ApiProfile CRUD + 拉模型（mock httpx）测试。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_profile(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/api-profiles",
        json={
            "name": "local-litellm",
            "base_url": "http://127.0.0.1:8000",
            "api_key": "sk-test-secret-1234",
            "default_model": "gpt-image-2",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["name"] == "local-litellm"
    assert created["base_url"] == "http://127.0.0.1:8000"
    assert created["api_key_masked"].endswith("1234")
    assert "secret" not in created["api_key_masked"]

    list_resp = await client.get("/api/api-profiles")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(it["id"] == created["id"] for it in items)


@pytest.mark.asyncio
async def test_update_profile_keeps_key_when_blank(client: AsyncClient) -> None:
    create = await client.post(
        "/api/api-profiles",
        json={
            "name": "P1",
            "base_url": "http://127.0.0.1:8000",
            "api_key": "sk-original-key-9999",
        },
    )
    pid = create.json()["id"]

    patch = await client.patch(
        f"/api/api-profiles/{pid}",
        json={"name": "P1-renamed", "api_key": ""},
    )
    assert patch.status_code == 200
    body = patch.json()
    assert body["name"] == "P1-renamed"
    # 原 key 末 4 位应当保持
    assert body["api_key_masked"].endswith("9999")


@pytest.mark.asyncio
async def test_update_profile_replaces_key_when_provided(client: AsyncClient) -> None:
    create = await client.post(
        "/api/api-profiles",
        json={
            "name": "P2",
            "base_url": "http://127.0.0.1:8000",
            "api_key": "sk-original-9999",
        },
    )
    pid = create.json()["id"]

    patch = await client.patch(
        f"/api/api-profiles/{pid}",
        json={"api_key": "sk-replaced-7777"},
    )
    assert patch.status_code == 200
    assert patch.json()["api_key_masked"].endswith("7777")


@pytest.mark.asyncio
async def test_delete_profile(client: AsyncClient) -> None:
    create = await client.post(
        "/api/api-profiles",
        json={
            "name": "P3",
            "base_url": "http://127.0.0.1:8000",
            "api_key": "sk-x",
        },
    )
    pid = create.json()["id"]
    del_resp = await client.delete(f"/api/api-profiles/{pid}")
    assert del_resp.status_code == 204

    miss = await client.delete(f"/api/api-profiles/{pid}")
    assert miss.status_code == 404


@pytest.mark.asyncio
async def test_fetch_models_happy(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    create = await client.post(
        "/api/api-profiles",
        json={
            "name": "PM",
            "base_url": "http://127.0.0.1:8000",
            "api_key": "sk-x",
        },
    )
    pid = create.json()["id"]

    captured: dict[str, Any] = {}

    class _MockResp:
        status_code = 200

        def __init__(self) -> None:
            self._body = {
                "object": "list",
                "data": [
                    {"id": "gpt-image-2", "object": "model", "owned_by": "openai"},
                    {"id": "stable-diffusion-3", "object": "model", "owned_by": "stability"},
                ],
            }

        def raise_for_status(self) -> None:
            pass

        def json(self) -> Any:
            return self._body

    class _MockClient:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> _MockClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str] | None = None) -> _MockResp:
            captured["url"] = url
            captured["headers"] = headers or {}
            return _MockResp()

    import app.services.external_models as ext_mod

    monkeypatch.setattr(ext_mod.httpx, "AsyncClient", _MockClient)

    resp = await client.post(f"/api/api-profiles/{pid}/models")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == json.loads(json.dumps(body))
    ids = [m["id"] for m in body["models"]]
    assert "gpt-image-2" in ids
    assert "stable-diffusion-3" in ids
    assert captured["url"] == "http://127.0.0.1:8000/v1/models"
    assert captured["headers"]["Authorization"] == "Bearer sk-x"


@pytest.mark.asyncio
async def test_fetch_models_unauthorized(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    create = await client.post(
        "/api/api-profiles",
        json={
            "name": "PM2",
            "base_url": "http://127.0.0.1:8000",
            "api_key": "bad",
        },
    )
    pid = create.json()["id"]

    class _MockResp:
        status_code = 401

        def raise_for_status(self) -> None:
            pass

        def json(self) -> Any:
            return {"error": "unauthorized"}

    class _MockClient:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> _MockClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str] | None = None) -> _MockResp:
            return _MockResp()

    import app.services.external_models as ext_mod

    monkeypatch.setattr(ext_mod.httpx, "AsyncClient", _MockClient)

    resp = await client.post(f"/api/api-profiles/{pid}/models")
    assert resp.status_code == 401
