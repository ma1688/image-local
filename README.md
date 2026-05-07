# 本地批量图片生成工作台

调用任意 OpenAI 兼容图像生成接口（例如 `http://127.0.0.1:8000/v1/images/generations`）的本地批量化工具。

- 后端：FastAPI 0.115 + Python 3.13 + Celery 5 + Redis 7 + SQLAlchemy 2 async + Pydantic v2
- 前端：React 19 + TypeScript 5.6 + Vite 6 + Ant Design 5 + Zustand + TanStack Query
- 启动：仅 Docker Compose（详见下文）

完整方案见 [`docs/方案设计.md`](./docs/方案设计.md)。

## 一键启动

需要本机已安装 Docker（与 Docker Compose v2，含 `docker compose` 子命令）。

```bash
# 1) 复制环境变量
cp .env.example .env

# 2) 一键拉起 redis / backend / worker / frontend
docker compose up
```

启动后访问：
- 前端：http://localhost:5178
- 后端：http://localhost:8787
- 健康检查：http://localhost:8787/api/health

## 目录

```
local_image/
├── docs/方案设计.md          # 完整方案（请先读）
├── docker-compose.yml
├── .env.example
├── backend/                  # FastAPI + Celery
└── frontend/                 # React + Vite
```

## 开发

- 后端代码挂载在容器内，`uvicorn --reload` 自动重启。
- 前端 `pnpm dev --host` 提供 HMR。
- Worker 修改代码需 `docker compose restart worker`。

## 进度

- [x] M0 脚手架（docker compose 起栈、健康检查）
- [ ] M1 数据层 + ApiProfile + 拉取模型
- [ ] M2 图片来源 + 模板 + 提示词
- [ ] M3 单图单候选闭环
- [ ] M4 Celery + SSE + 多并发 + 重试 + 取消
- [ ] M5 结果区
- [ ] M6 历史记录
- [ ] M7 边界打磨
