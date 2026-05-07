"""Alembic env：使用项目 Settings 与 sync 引擎进行迁移。"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.db import Base
from app.core.settings import get_settings

# 触发 model 注册
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
settings.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

# 迁移用同步驱动（sqlite 即可），保证 alembic 与 SQLAlchemy 1.4 风格 API 兼容
sync_db_url = f"sqlite:///{settings.db_path.as_posix()}"
config.set_main_option("sqlalchemy.url", sync_db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=sync_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
