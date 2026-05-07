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
      '/api/sse': {
        target: BACKEND_TARGET,
        changeOrigin: true,
        ws: false,
        configure: (proxy) => {
          // SSE: 关闭代理缓冲，避免事件被攒着发出
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache, no-transform';
            proxyRes.headers['x-accel-buffering'] = 'no';
          });
        },
      },
      '/api': {
        target: BACKEND_TARGET,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
});
