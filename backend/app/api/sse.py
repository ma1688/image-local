"""SSE 端点：订阅一个 Job 的事件流。

行为：
- 首次连接默认回放最近 200 条历史事件，然后阻塞等新事件。
- 客户端可通过 `Last-Event-ID` 头或 ``?last_id=`` query 指定从哪条续推；
  传 ``$`` 表示只看新事件。
- 心跳：每 15 秒发送一次 ``: ping``，避免反代/浏览器中断。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.services.event_bus import history, read_stream

router = APIRouter(prefix="/jobs", tags=["sse"])


async def _event_stream(
    request: Request, job_id: int, last_id: str
) -> AsyncIterator[dict[str, str]]:
    # 1. 首次连接：回放历史
    cursor = last_id
    if cursor in ("", "0", "0-0", "history"):
        replay = await history(job_id, count=200)
        for entry_id, payload in replay:
            yield {
                "event": str(payload.get("event", "message")),
                "id": entry_id,
                "data": json.dumps(payload, default=str),
            }
        cursor = replay[-1][0] if replay else "$"
    elif cursor == "$":
        # 仅看新事件；无需回放
        pass
    # 否则视为客户端给的具体 entry_id，从该 id 之后开始

    # 2. 持续阻塞读
    while True:
        if await request.is_disconnected():
            return
        try:
            entries = await read_stream(job_id, last_id=cursor, block_ms=5000, count=50)
        except Exception as exc:  # 包括 redis 连接失败
            yield {
                "event": "error",
                "data": json.dumps({"message": f"read_stream failed: {exc}"}),
            }
            await asyncio.sleep(2)
            continue

        if not entries:
            # 心跳
            yield {"event": "ping", "data": "{}"}
            continue

        for entry_id, payload in entries:
            yield {
                "event": str(payload.get("event", "message")),
                "id": entry_id,
                "data": json.dumps(payload, default=str),
            }
            cursor = entry_id


@router.get("/{job_id}/events")
async def subscribe_events(
    job_id: int,
    request: Request,
    last_id: str = Query(default="history"),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> EventSourceResponse:
    """SSE 推送 job 的运行事件。"""
    cursor = last_event_id or last_id
    return EventSourceResponse(
        _event_stream(request, job_id, cursor),
        ping=15,  # sse_starlette 自带 keepalive
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
