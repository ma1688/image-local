FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/uv-venv \
    PATH=/opt/uv-venv/bin:$PATH

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libjpeg62-turbo-dev \
        zlib1g-dev \
        libwebp-dev \
        libpng-dev \
 && rm -rf /var/lib/apt/lists/*

# Install uv (Astral, fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv

WORKDIR /app

# 先拷贝依赖描述文件以利用 Docker 层缓存
COPY pyproject.toml ./
COPY uv.lock* ./

# Sync 依赖（包含 dev 组，便于容器内跑 pytest/ruff）
RUN uv sync --frozen --no-install-project 2>/dev/null \
 || uv sync --no-install-project

COPY . .

EXPOSE 8787

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
