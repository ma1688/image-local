"""Celery 应用入口。worker 与 web 进程都从这里 import。"""

from __future__ import annotations

from celery import Celery

from .settings import get_settings

_settings = get_settings()

celery_app = Celery(
    "local_image",
    broker=_settings.CELERY_BROKER_URL,
    backend=_settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.generate"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)

# M4 阶段会取消下面这行的注释以注册 worker tasks
# celery_app.autodiscover_tasks(["app.workers"])
