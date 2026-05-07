"""Celery 应用入口。worker 与 web 进程都从这里 import。"""

from __future__ import annotations

from typing import Any

from celery import Celery
from celery.signals import worker_init, worker_process_init

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


def _setup_worker_logging(**_kwargs: Any) -> None:
    """worker 进程启动时调一次 ``configure_logging``。

    保证 task 代码里 ``loguru.logger.info(...)`` 在 worker 中也走带
    ``enqueue=True`` 的 sink，避免 ``-P threads`` 下多线程并发记录因 sink
    锁竞争互相阻塞。同时让 stdlib bridge 的 ``_InterceptHandler`` 在 worker
    主进程上注册（celery 自身的 ``hijack_root_logger`` 行为不变，仅追加我
    们的 handler 到 root logger）。
    """
    from app.core.logging import configure_logging

    configure_logging()


worker_init.connect(_setup_worker_logging)
worker_process_init.connect(_setup_worker_logging)


# M4 阶段会取消下面这行的注释以注册 worker tasks
# celery_app.autodiscover_tasks(["app.workers"])
