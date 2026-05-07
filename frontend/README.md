# frontend

React 19 + Vite 6 + TypeScript 5.7 + Ant Design 5 + Zustand + TanStack Query。

由根目录 `docker-compose.yml` 一键拉起。

## 容器内开发命令

容器启动时已自动执行 `pnpm install`，HMR 默认开启，本地修改源码即热更。

调试用：

```bash
docker compose exec frontend sh
# 容器内：
pnpm typecheck
pnpm lint
pnpm test
```

## 宿主机直接运行（可选）

```powershell
corepack enable
corepack use pnpm@9.15.0
pnpm install
pnpm dev
```
