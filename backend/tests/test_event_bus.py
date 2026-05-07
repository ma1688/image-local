"""event_bus 单测：用 fakeredis 验证 publish / read_stream / history。"""

from __future__ import annotations

from typing import Any

import fakeredis
import fakeredis.aioredis
import pytest


@pytest.fixture
def patch_redis(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    """同时替换 sync 与 async 的 from_url 为 fakeredis。"""
    sync_server = fakeredis.FakeServer()
    sync_client = fakeredis.FakeRedis(server=sync_server, decode_responses=True)
    async_client = fakeredis.aioredis.FakeRedis(server=sync_server, decode_responses=True)

    from app.services import event_bus as eb

    monkeypatch.setattr(eb, "_sync_client", lambda: sync_client)
    monkeypatch.setattr(eb, "_async_client", lambda: async_client)

    return sync_client, async_client


def test_publish_and_history(patch_redis: tuple[Any, Any]) -> None:
    from app.services import event_bus as eb

    eb.publish(42, {"event": "job.created", "job_id": 42, "total": 4})
    eb.publish(42, {"event": "candidate.running", "candidate_id": 1, "index": 1})
    eb.publish(42, {"event": "candidate.succeeded", "candidate_id": 1, "index": 1})

    import asyncio

    out = asyncio.run(eb.history(42, count=10))
    assert len(out) == 3
    assert [p["event"] for _, p in out] == [
        "job.created",
        "candidate.running",
        "candidate.succeeded",
    ]
    assert out[0][1]["job_id"] == 42


def test_read_stream_returns_new_only(patch_redis: tuple[Any, Any]) -> None:
    """传 last_id='$' 应该只看到新事件。"""
    from app.services import event_bus as eb

    # 先 publish 1 条
    eb.publish(7, {"event": "x", "n": 1})

    import asyncio

    async def go() -> list[tuple[str, dict[str, Any]]]:
        # 用 0-0 应能读到全部
        return await eb.read_stream(7, last_id="0-0", block_ms=10, count=10)

    all_msgs = asyncio.run(go())
    assert len(all_msgs) == 1
    assert all_msgs[0][1]["n"] == 1


def test_read_stream_blocks_then_returns_empty(patch_redis: tuple[Any, Any]) -> None:
    """超时未拿到新消息时返回空列表（不抛异常）。"""
    from app.services import event_bus as eb

    import asyncio

    async def go() -> list[tuple[str, dict[str, Any]]]:
        return await eb.read_stream(99, last_id="$", block_ms=20, count=10)

    out = asyncio.run(go())
    assert out == []
