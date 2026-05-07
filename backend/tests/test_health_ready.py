"""测试 /api/health 与 /api/ready：依赖故障时 ready 返回 503，且 request_id 头注入。"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_ok_and_request_id_header(client: AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    # 中间件应注入 X-Request-Id
    assert "x-request-id" in {k.lower() for k in r.headers.keys()}
    rid = r.headers.get("X-Request-Id") or r.headers.get("x-request-id")
    assert rid and len(rid) == 8


@pytest.mark.asyncio
async def test_ready_503_when_redis_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模拟 redis 不可用 -> ready 应返回 503，但内部 detail 不为空。"""
    from app.api import health as health_mod

    async def _fake_redis() -> Any:
        return health_mod.ReadyCheck(ok=False, detail="simulated down")

    monkeypatch.setattr(health_mod, "_check_redis", _fake_redis)
    r = await client.get("/api/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["ready"] is False
    assert body["redis"]["ok"] is False
    assert body["redis"]["detail"] == "simulated down"
    # db / fernet 在测试环境下应正常
    assert body["db"]["ok"] is True
    assert body["fernet"]["ok"] is True


@pytest.mark.asyncio
async def test_ready_200_when_all_ok(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import health as health_mod

    async def _fake_ok_redis() -> Any:
        return health_mod.ReadyCheck(ok=True)

    monkeypatch.setattr(health_mod, "_check_redis", _fake_ok_redis)
    r = await client.get("/api/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["db"]["ok"] is True
    assert body["redis"]["ok"] is True
    assert body["fernet"]["ok"] is True
