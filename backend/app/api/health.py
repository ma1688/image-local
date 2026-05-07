"""健康检查与就绪检查端点。

- ``/api/health``  liveness：进程能响应即 200，并附带依赖快照（不阻断）。
- ``/api/ready``   readiness：依赖（db / redis / fernet）全部 ok 才 200，否则 503。

ready 用于 K8s readiness / 负载均衡摘除流量，避免请求打到尚未真正可用的实例。
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import text

from app.core.crypto import encrypt
from app.core.db import engine
from app.core.settings import get_settings

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    task_backend: str
    db_ok: bool
    redis_ok: bool


class ReadyCheck(BaseModel):
    ok: bool
    detail: str | None = None


class ReadyResponse(BaseModel):
    ready: bool
    db: ReadyCheck
    redis: ReadyCheck
    fernet: ReadyCheck


async def _check_db() -> ReadyCheck:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return ReadyCheck(ok=True)
    except Exception as exc:
        return ReadyCheck(ok=False, detail=str(exc)[:200])


async def _check_redis() -> ReadyCheck:
    try:
        import redis.asyncio as aioredis  # local import to avoid hard dep at boot

        client = aioredis.from_url(get_settings().REDIS_URL)
        try:
            ok = bool(await client.ping())
            return ReadyCheck(ok=ok)
        finally:
            await client.aclose()
    except Exception as exc:
        return ReadyCheck(ok=False, detail=str(exc)[:200])


def _check_fernet() -> ReadyCheck:
    """fernet 可用性 = 能加载 key 且能完成一次 encrypt 调用。"""
    try:
        encrypt("__readyz_probe__")
        return ReadyCheck(ok=True)
    except Exception as exc:
        return ReadyCheck(ok=False, detail=str(exc)[:200])


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness：始终 200，附带依赖快照供运维参考。"""
    settings = get_settings()
    from app import __version__

    db = await _check_db()
    redis = await _check_redis()
    return HealthResponse(
        status="ok",
        version=__version__,
        task_backend=settings.TASK_BACKEND,
        db_ok=db.ok,
        redis_ok=redis.ok,
    )


# 把 readiness 暴露在与 /api/health 同一前缀下，路径为 /api/health/ready；同时
# 在 main.py 注册一个简化别名 /api/ready 以贴合常见运维约定。
@router.get("/ready", response_model=ReadyResponse)
async def ready(response: Response) -> ReadyResponse:
    db = await _check_db()
    redis = await _check_redis()
    fernet = _check_fernet()
    all_ok = db.ok and redis.ok and fernet.ok
    if not all_ok:
        response.status_code = 503
    return ReadyResponse(ready=all_ok, db=db, redis=redis, fernet=fernet)
