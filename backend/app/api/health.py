from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.core.db import engine
from app.core.settings import get_settings

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    task_backend: str
    db_ok: bool
    redis_ok: bool


async def _check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _check_redis() -> bool:
    try:
        import redis.asyncio as aioredis  # local import to avoid hard dep at boot

        client = aioredis.from_url(get_settings().REDIS_URL)
        try:
            return bool(await client.ping())
        finally:
            await client.aclose()
    except Exception:
        return False


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    from app import __version__

    return HealthResponse(
        status="ok",
        version=__version__,
        task_backend=settings.TASK_BACKEND,
        db_ok=await _check_db(),
        redis_ok=await _check_redis(),
    )
