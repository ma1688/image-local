FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/uv-venv \
    PATH=/opt/uv-venv/bin:$PATH

ARG PIP_INDEX_URL=https://pypi.org/simple

# Install uv from PyPI instead of ghcr.io, so the build does not depend on GHCR DNS/access.
RUN python -m pip install --no-cache-dir --index-url "$PIP_INDEX_URL" "uv==0.10.*"

WORKDIR /app

FROM base AS deps

# 先拷贝依赖描述文件以利用 Docker 层缓存。
COPY pyproject.toml ./
COPY uv.lock* ./

# Sync 依赖（包含 dev 组，便于容器内跑 pytest/ruff）。
# 依赖均优先使用 wheel，避免 apt/build-essential 导致无缓存构建长时间卡住。
RUN uv sync --frozen --no-install-project \
 || uv sync --no-install-project

FROM base AS dev

COPY --from=deps /opt/uv-venv /opt/uv-venv

COPY . .

EXPOSE 8787

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
