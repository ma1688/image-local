"""基于 Redis Streams 的轻量事件总线。

设计要点（方案 5.4 节）：
- 每个 Job 一个 Stream，key = ``li:job:{job_id}:events``
- 事件 entry 仅包含一个字段 ``payload``，值为 JSON 字符串
- 读取支持 ``last_id``（断线续推）；首次连接传 ``$`` 表示只看新事件，传 ``0-0`` 表示从头读
- ``maxlen=500`` + ``approximate=True``，避免 stream 无限增长
- 同步 publish（Celery worker 内调用），异步 read（FastAPI SSE 内调用）
"""

from __future__ import annotations

import json
from typing import Any

import redis as redis_sync
import redis.asyncio as redis_async

from app.core.settings import get_settings


def stream_key(job_id: int) -> str:
    return f"li:job:{job_id}:events"


def _sync_client() -> redis_sync.Redis:
    s = get_settings()
    return redis_sync.from_url(s.REDIS_URL, decode_responses=True)


def _async_client() -> redis_async.Redis:
    s = get_settings()
    return redis_async.from_url(s.REDIS_URL, decode_responses=True)


def publish(job_id: int, payload: dict[str, Any], *, maxlen: int = 500) -> str:
    """同步 publish（在 Celery worker / web 进程内都可用）。返回新 entry id。"""
    cli = _sync_client()
    try:
        return cli.xadd(  # type: ignore[no-any-return]
            stream_key(job_id),
            {"payload": json.dumps(payload, default=str)},
            maxlen=maxlen,
            approximate=True,
        )
    finally:
        cli.close()


def reset_stream(job_id: int) -> None:
    """删除某个 job 的事件流。

    SQLite 开发库可能被删除/重建后复用自增 id，而 Redis Stream 仍保留旧的
    ``li:job:{id}:events``。新 job 创建前清掉同 id 旧流，避免前端首次订阅
    ``history`` 时读到旧 job.terminated，造成 SSE 反复 close/reconnect。
    """
    cli = _sync_client()
    try:
        cli.delete(stream_key(job_id))
    finally:
        cli.close()


async def read_stream(
    job_id: int,
    *,
    last_id: str = "$",
    block_ms: int = 15000,
    count: int = 50,
) -> list[tuple[str, dict[str, Any]]]:
    """异步阻塞读 Redis Stream。

    返回 (entry_id, payload_dict) 列表；空列表表示超时（block_ms 内无新消息）。
    """
    cli = _async_client()
    try:
        resp: list[tuple[str, list[tuple[str, dict[str, str]]]]] | None = await cli.xread(
            {stream_key(job_id): last_id},
            block=block_ms,
            count=count,
        )
    finally:
        await cli.aclose()

    if not resp:
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for _stream_name, entries in resp:
        for entry_id, fields in entries:
            raw = fields.get("payload") if isinstance(fields, dict) else None
            try:
                obj = json.loads(raw) if raw else {}
            except (TypeError, ValueError):
                obj = {"raw": raw}
            out.append((entry_id, obj))
    return out


async def history(job_id: int, *, count: int = 200) -> list[tuple[str, dict[str, Any]]]:
    """异步取该 stream 的最近 count 条历史。前端首次连接时使用。"""
    cli = _async_client()
    try:
        # XRANGE 返回最早->最近，再裁剪
        entries: list[tuple[str, dict[str, str]]] = await cli.xrange(
            stream_key(job_id), min="-", max="+", count=count
        )
    finally:
        await cli.aclose()

    out: list[tuple[str, dict[str, Any]]] = []
    for entry_id, fields in entries:
        raw = fields.get("payload") if isinstance(fields, dict) else None
        try:
            obj = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            obj = {"raw": raw}
        out.append((entry_id, obj))
    return out
