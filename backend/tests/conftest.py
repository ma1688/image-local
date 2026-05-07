"""共用 fixtures。

- 把 APP_DATA_DIR 指到临时目录，确保每次测试用全新 SQLite + Fernet key。
- 提供异步 httpx.AsyncClient，绑定 ASGITransport。
- 重置全局 lru_cache 单例（settings, fernet）。
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session", autouse=True)
def _isolate_data_dir() -> Path:
    tmp_root = Path(tempfile.mkdtemp(prefix="li_test_"))
    os.environ["APP_DATA_DIR"] = str(tmp_root)
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
    os.environ["ALLOW_ANY_DIR_SCAN"] = "true"  # 默认所有测试都开放扫描
    for mod_name in list(sys.modules):
        if mod_name.startswith("app."):
            del sys.modules[mod_name]
    return tmp_root


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """每个测试前清空 Settings lru_cache，避免 monkeypatch 互相污染。"""
    try:
        from app.core import settings as settings_mod

        settings_mod.get_settings.cache_clear()
    except Exception:
        pass


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """每个测试用例都构建一个新的 FastAPI app（独立 lifespan / DB）。"""
    # 通过 reload 清空 settings/fernet/db 的 lru_cache
    importlib.invalidate_caches()
    for mod_name in list(sys.modules):
        if mod_name.startswith("app."):
            del sys.modules[mod_name]

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 触发 lifespan 启动（包含 alembic upgrade + builtin templates seeding）
        async with app.router.lifespan_context(app):
            yield ac
