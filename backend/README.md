# backend

FastAPI + Celery + Redis + SQLite 的后端服务。

## 模块

```text
app/
├── api/              # REST API 与 SSE：jobs/images/templates/api-profiles/files/storage
├── core/             # settings/db/celery_app/logging/crypto
├── models/           # SQLAlchemy ORM
├── schemas/          # Pydantic v2 schemas
├── services/         # job_runner/event_bus/openai_image/storage/prompt_template
└── tasks/            # Celery task: generate_one_candidate
```

## 本地运行

需要 Redis 已启动。

```powershell
cd D:\py_project\local_image\backend

$env:APP_DATA_DIR = "D:\py_project\local_image\backend\data"
$env:TASK_BACKEND = "celery"
$env:REDIS_URL = "redis://127.0.0.1:6379/0"
$env:CELERY_BROKER_URL = "redis://127.0.0.1:6379/1"
$env:CELERY_RESULT_BACKEND = "redis://127.0.0.1:6379/2"
$env:CORS_ORIGINS = "http://localhost:5173"

uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8787
```

另开 worker：

```powershell
cd D:\py_project\local_image\backend

$env:APP_DATA_DIR = "D:\py_project\local_image\backend\data"
$env:TASK_BACKEND = "celery"
$env:REDIS_URL = "redis://127.0.0.1:6379/0"
$env:CELERY_BROKER_URL = "redis://127.0.0.1:6379/1"
$env:CELERY_RESULT_BACKEND = "redis://127.0.0.1:6379/2"

uv run celery -A app.core.celery_app.celery_app worker -l INFO -P solo
```

## 图像接口选择

- `gpt-image-*` + 参考图：`POST {base_url}/v1/images/edits`
- 其它模型：`POST {base_url}/v1/images/generations`
- 模型列表：`GET {base_url}/v1/models`

## 测试

```powershell
uv run pytest
```
