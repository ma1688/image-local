"""M0 烟囱测试：仅校验 import 链通畅 + 配置可加载。

更深的健康检查留待 M1 起接入 httpx ASGITransport 做真实 HTTP 测试。
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_DATA_DIR", "./_tmp_data")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def test_settings_loads() -> None:
    from app.core.settings import get_settings

    s = get_settings()
    assert s.TASK_BACKEND in {"celery", "asyncio"}
    assert s.db_url.startswith("sqlite+aiosqlite:///")


def test_app_imports() -> None:
    from app.main import app

    assert app.title == "local-image"
    routes = {r.path for r in app.routes}
    assert "/api/health" in routes


def test_celery_app_imports() -> None:
    from app.core.celery_app import celery_app

    assert celery_app.main == "local_image"
