from __future__ import annotations

import logging
import sys

from loguru import logger

from .settings import get_settings


class _InterceptHandler(logging.Handler):
    """把 stdlib logging 转发到 loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except (ValueError, AttributeError):
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        try:
            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())
        except Exception:
            sys.stderr.write(f"{record.levelname}: {record.getMessage()}\n")


def configure_logging() -> None:
    """配置 loguru 与 stdlib bridge；不影响 uvicorn 自己的 handler。"""
    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        backtrace=True,
        diagnose=False,
    )
    # 仅安装到 root logger，不替换任何已有 handler，避免吞掉 uvicorn 默认输出。
    root = logging.getLogger()
    if not any(isinstance(h, _InterceptHandler) for h in root.handlers):
        root.addHandler(_InterceptHandler())
    root.setLevel(logging.INFO)
