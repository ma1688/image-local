from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config as AlembicConfig
from loguru import logger
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from alembic import command

from .settings import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy ORM base."""


_settings = get_settings()

engine = create_async_engine(
    _settings.db_url,
    echo=False,
    future=True,
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _):  # type: ignore[no-untyped-def]
    """SQLite WAL + busy_timeout（参见方案 8.7 节临界情况）。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """业务代码使用的事务上下文。"""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _alembic_config() -> AlembicConfig:
    """构造 Alembic Config，指向项目内的 alembic.ini。"""
    base = Path(__file__).resolve().parents[2]  # backend/
    cfg = AlembicConfig(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{_settings.db_path.as_posix()}")
    return cfg


async def upgrade_db_to_head() -> None:
    """启动时自动迁移到最新版本（alembic upgrade head）。"""
    _settings.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg = _alembic_config()
    logger.info("running alembic upgrade head ...")
    # alembic 命令是同步阻塞的；放到默认线程池避免阻塞 event loop。
    import asyncio

    await asyncio.to_thread(command.upgrade, cfg, "head")
    logger.info("alembic upgrade head done.")
