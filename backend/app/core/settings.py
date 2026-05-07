from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置；优先级 env > .env > 默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_DATA_DIR: Path = Path("/app/data")
    LOG_LEVEL: str = "INFO"

    TASK_BACKEND: Literal["celery", "asyncio"] = "celery"

    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    SECRET_FERNET_KEY: str = ""
    ALLOW_ANY_DIR_SCAN: bool = True

    CORS_ORIGINS: str = "http://localhost:5173"

    SCAN_FILE_LIMIT: int = 1000
    UPLOAD_MAX_BYTES: int = 50 * 1024 * 1024
    SOURCE_IMAGE_MAX_BYTES: int = 20 * 1024 * 1024
    DEFAULT_TASK_TIMEOUT_SECONDS: int = 1800

    # 数据目录使用警戒阈值（字节）。仅做 UI 警告，不会自动清理。
    # 默认 5 GiB。运维可在 .env 中按机器空间放大或缩小。
    STORAGE_WARN_BYTES: int = 5 * 1024 * 1024 * 1024
    # 数据目录硬上限（字节，默认 0 = 不限制）。设置后超过会让上传/创建任务报 4xx。
    STORAGE_HARD_LIMIT_BYTES: int = 0

    @property
    def outputs_dir(self) -> Path:
        return self.APP_DATA_DIR / "outputs"

    @property
    def thumbs_dir(self) -> Path:
        return self.APP_DATA_DIR / "thumbs"

    @property
    def db_path(self) -> Path:
        return self.APP_DATA_DIR / "app.db"

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path.as_posix()}"

    @property
    def fernet_key_path(self) -> Path:
        return self.APP_DATA_DIR / ".fernet_key"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
