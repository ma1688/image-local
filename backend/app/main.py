from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app import __version__
from app.api.api_profiles import router as api_profiles_router
from app.api.files import router as files_router
from app.api.health import router as health_router
from app.api.images import router as images_router
from app.api.jobs import router as jobs_router
from app.api.sse import router as sse_router
from app.api.templates import router as templates_router
from app.core.db import upgrade_db_to_head
from app.core.logging import configure_logging
from app.core.settings import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    settings.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    settings.thumbs_dir.mkdir(parents=True, exist_ok=True)
    await upgrade_db_to_head()
    from app.services.template_seed import seed_builtin_templates

    await seed_builtin_templates()
    logger.info("backend started, version={}, data_dir={}", __version__, settings.APP_DATA_DIR)
    yield
    logger.info("backend stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="local-image",
        description="本地批量图片生成工作台",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(templates_router, prefix="/api")
    app.include_router(api_profiles_router, prefix="/api")
    app.include_router(images_router, prefix="/api")
    app.include_router(files_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(sse_router, prefix="/api")
    return app


app = create_app()
