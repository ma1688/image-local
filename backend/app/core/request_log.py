"""结构化请求日志中间件。

每次请求记录：
- request_id: 8 位短 hash，在响应头 ``X-Request-Id`` 回写
- method / path / query_count
- status / duration_ms
- client_ip （仅日志，不持久化）

设计取舍：
- 不在这里持久化日志，避免 IO 阻塞 + 数据增长。运维需要持久化时由
  日志采集器（promtail / fluent-bit / docker logs 驱动）兜住。
- 排除 SSE 长连接（``/api/jobs/.../events``）的耗时统计，因为它会一直挂着。
- 排除 ``/api/health`` 的"成功"日志，避免 readiness/liveness 把日志刷屏；
  仅当 health 返回非 2xx 时打错误日志。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_HEALTH_QUIET_PATHS = {"/api/health", "/api/health/ready", "/api/ready"}


def _short_request_id() -> str:
    return uuid.uuid4().hex[:8]


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = _short_request_id()
        # 注入到 scope 让下游 handler / dependency 可读取
        request.scope["request_id"] = rid

        path = request.url.path
        # SSE 流路径不打开始/结束日志（耗时无意义、日志会刷屏）
        is_sse = path.startswith("/api/jobs/") and path.endswith("/events")

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Request-Id"] = rid
        status_code = response.status_code

        # health/readiness 成功调用静默；失败仍记录
        quiet = path in _HEALTH_QUIET_PATHS and 200 <= status_code < 300
        if quiet:
            return response

        level = "INFO"
        if status_code >= 500:
            level = "ERROR"
        elif status_code >= 400:
            level = "WARNING"

        client_ip = request.client.host if request.client else "-"
        query_count = len(request.query_params)
        tag = "sse_open" if is_sse else "req"

        logger.bind(request_id=rid).log(
            level,
            "[{tag}] {method} {path} status={status} {duration:.1f}ms "
            "client={ip} q={q}",
            tag=tag,
            method=request.method,
            path=path,
            status=status_code,
            duration=duration_ms,
            ip=client_ip,
            q=query_count,
        )
        return response
