# backend

FastAPI + Celery + Redis + SQLAlchemy 2 async + Pydantic v2.

由根目录 `docker-compose.yml` 一键拉起，无需在宿主机单独运行。

如需在宿主机本地跑（不推荐）：

```powershell
uv sync
uv run uvicorn app.main:app --reload --port 8787
```

但 Celery worker 仍需 Redis，建议直接用 docker compose。
