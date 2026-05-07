from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每请求一个 session，请求完成后自动 close（commit/rollback 由路由内部决定）。"""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


DbDep = Depends(get_db)
