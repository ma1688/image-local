# frontend

React 19 + Vite 6 + TypeScript + Ant Design 5。

## 模块

```text
src/
├── api/          # REST client / endpoints / SSE client / types
├── components/   # API 配置、图片来源、生成控制、日志、结果、历史
├── pages/        # Workbench
└── store/        # Zustand stores
```

## 本地运行

```powershell
cd D:\py_project\local_image\frontend

$env:VITE_API_BASE = "/api"
$env:VITE_BACKEND_TARGET = "http://127.0.0.1:8787"

pnpm install
pnpm dev
```

访问：http://localhost:5173

## Docker Compose

根目录执行：

```bash
docker compose up --build
```

Compose 暴露端口为：http://localhost:5178

## 测试

```powershell
pnpm typecheck
pnpm test
```

## SSE 行为

`LogStream` 只在当前 job 非终态时订阅 `/api/jobs/{id}/events`。收到终态后关闭连接，避免终态 job 继续重连。store 会丢弃非当前 job_id 的历史事件，避免旧 Redis Stream 污染当前任务。
