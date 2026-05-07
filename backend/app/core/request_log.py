"""结构化请求日志中间件（纯 ASGI 实现）。

每次请求记录：
- request_id: 8 位短 hash，在响应头 ``X-Request-Id`` 回写并写入 ``scope``
- method / path / query_count
- status / duration_ms
- client_ip （仅日志，不持久化）

设计取舍：
- 不在这里持久化日志，避免 IO 阻塞 + 数据增长。运维需要持久化时由
  日志采集器（promtail / fluent-bit / docker logs 驱动）兜住。
- 排除 ``/api/health`` 的"成功"日志，避免 readiness/liveness 把日志刷屏；
  仅当 health 返回非 2xx 时打错误日志。
- SSE 长连接：在响应**结束**时（客户端断开 / 服务端 generator 终止）才记录
  duration，tag 为 ``sse_close``；不会因为 ``await call_next`` 的语义把每条
  日志都阻塞到连接结束（旧的 BaseHTTPMiddleware 实现就是这样的，且对流式
  响应有官方文档警告）。

为什么不用 ``starlette.middleware.base.BaseHTTPMiddleware`` / ``@app.middleware``：
两者实际是同一实现，会用 anyio task group 包住整个请求/响应生命周期；
对 SSE 这类长流式响应，每条连接都额外占一个任务并放大调度开销。改成直接
处理 ``scope/receive/send`` 后，SSE 路径上几乎没有额外开销。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qsl

from loguru import logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HEALTH_QUIET_PATHS = {"/api/health", "/api/health/ready", "/api/ready"}


def _short_request_id() -> str:
    return uuid.uuid4().hex[:8]


def _is_sse_path(path: str) -> bool:
    return path.startswith("/api/jobs/") and path.endswith("/events")


class RequestLogMiddleware:
    """纯 ASGI 中间件：注入 request_id + 结束时打一条结构化日志。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = _short_request_id()
        scope["request_id"] = rid

        path: str = scope.get("path", "") or ""
        is_sse = _is_sse_path(path)

        status_holder: dict[str, int] = {"code": 0}
        response_started = False

        send_wrapper: Callable[[Message], Awaitable[None]]

        async def _send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                status_holder["code"] = int(message.get("status", 0) or 0)
                # 注入 X-Request-Id；用 list 拷贝避免对调用方共享列表的副作用
                headers = list(message.get("headers", []) or [])
                headers.append((b"x-request-id", rid.encode("ascii")))
                # 让 message 透传时携带新的 headers
                message = {**message, "headers": headers}
                response_started = True
            await send(message)

        send_wrapper = _send

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            status_code = status_holder["code"]

            # 客户端断连等情况下 ASGI app 可能没有发出 http.response.start，
            # 此时无法判断 status；记一条 disconnect 日志
            if not response_started:
                logger.bind(request_id=rid).warning(
                    "[disconnect] {method} {path} {duration:.1f}ms",
                    method=scope.get("method", ""),
                    path=path,
                    duration=duration_ms,
                )
                return

            quiet = path in _HEALTH_QUIET_PATHS and 200 <= status_code < 300
            if quiet:
                return

            level = "INFO"
            if status_code >= 500:
                level = "ERROR"
            elif status_code >= 400:
                level = "WARNING"

            client = scope.get("client") or None
            client_ip = client[0] if client else "-"
            qs: bytes = scope.get("query_string", b"") or b""
            query_count = (
                len(parse_qsl(qs.decode("latin-1"), keep_blank_values=True)) if qs else 0
            )
            tag = "sse_close" if is_sse else "req"

            logger.bind(request_id=rid).log(
                level,
                "[{tag}] {method} {path} status={status} {duration:.1f}ms "
                "client={ip} q={q}",
                tag=tag,
                method=scope.get("method", ""),
                path=path,
                status=status_code,
                duration=duration_ms,
                ip=client_ip,
                q=query_count,
            )
