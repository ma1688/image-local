import type { ApiErrorBody } from './types';

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';

export class ApiError extends Error {
  status: number;
  detail: string;
  body: ApiErrorBody | null;

  constructor(status: number, detail: string, body: ApiErrorBody | null) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE' | 'PUT';
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const init: RequestInit = {
    method: opts.method ?? 'GET',
    signal: opts.signal,
    headers: {
      Accept: 'application/json',
      ...(opts.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...opts.headers,
    },
  };
  if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
  }

  const resp = await fetch(url, init);
  if (resp.status === 204) {
    return undefined as T;
  }

  const text = await resp.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }

  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
      const d = (parsed as ApiErrorBody).detail;
      if (typeof d === 'string') detail = d;
      else if (d) detail = JSON.stringify(d);
    } else if (text) {
      detail = text;
    }
    throw new ApiError(resp.status, detail, (parsed as ApiErrorBody | null) ?? null);
  }

  return parsed as T;
}

export const api = {
  get: <T>(path: string, opts?: RequestOptions) => request<T>(path, { ...opts, method: 'GET' }),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: 'PATCH', body }),
  delete: <T>(path: string, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: 'DELETE' }),
};
