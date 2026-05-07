import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const BACKEND_TARGET = process.env.VITE_BACKEND_TARGET ?? 'http://backend:8787';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    watch: {
      usePolling: true,
      interval: 500,
    },
    proxy: {
      // 统一在 /api 上挂代理。原本想给 SSE 单独写一条 `/api/sse`，但实际 SSE
      // 端点是 `/api/jobs/{id}/events`，前缀匹配不到，会退到这条通用规则。
      // 现改为：仅当后端响应为 text/event-stream 时再注入 SSE 友好的响应头，
      // 避免 node-http-proxy 默认对 chunked 响应补 `connection: close`，
      // 否则浏览器 EventSource 会以为连接关闭并反复重连，UI 卡在「连接中…」。
      '/api': {
        target: BACKEND_TARGET,
        changeOrigin: true,
        ws: false,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            const contentType = String(proxyRes.headers['content-type'] ?? '');
            if (contentType.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache, no-transform';
              proxyRes.headers['x-accel-buffering'] = 'no';
              proxyRes.headers['connection'] = 'keep-alive';
            }
          });
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
});
