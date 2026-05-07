// 与后端 publish 出来的事件类型对齐
export type SseEvent =
  | { event: 'job.created'; job_id: number; total: number; candidates_per_image: number; items: { path: string; name: string }[] }
  | { event: 'job.updated'; job_id: number; status: string; succeeded: number; failed: number; total: number }
  | { event: 'job.terminated'; job_id: number; status: string; succeeded: number; failed: number; total: number }
  | { event: 'candidate.running'; candidate_id: number; item_id: number; index: number; attempt: number; source_name: string }
  | { event: 'candidate.retry'; candidate_id: number; item_id: number; index: number; attempt: number; error: string; source_name: string }
  | { event: 'candidate.succeeded'; candidate_id: number; item_id: number; index: number; output_path: string; source_name: string }
  | { event: 'candidate.failed'; candidate_id: number; item_id: number; index: number; attempt: number; error: string; source_name: string }
  | { event: 'candidate.selected'; candidate_id: number; item_id: number; is_selected: boolean }
  | { event: 'ping' }
  | { event: 'error'; message: string };

export interface SseEntry {
  id: string;
  receivedAt: string;
  payload: SseEvent;
}

export type SseConnectionState =
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed';

export interface SseHandle {
  close: () => void;
  /** 当前连接状态（同步快照） */
  getState: () => SseConnectionState;
}

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';

const KNOWN_EVENTS = [
  'job.created',
  'job.updated',
  'job.terminated',
  'candidate.running',
  'candidate.retry',
  'candidate.succeeded',
  'candidate.failed',
  'candidate.selected',
  'ping',
  'error',
] as const;

// 重连退避：1s / 2s / 4s / 8s / 15s 最大；连续失败 30 次后停止重连。
const BACKOFF_SCHEDULE = [1000, 2000, 4000, 8000, 15000];
const MAX_RETRY = 30;

export interface SubscribeOptions {
  /** 起始 last_id（首次连接时使用），默认 ``history`` 让后端回放历史事件 */
  initialLastId?: string;
  /** 连接状态变化回调，便于 UI 显示 reconnecting 提示 */
  onStateChange?: (state: SseConnectionState) => void;
}

export function subscribeJobEvents(
  jobId: number,
  onEntry: (entry: SseEntry) => void,
  opts?: SubscribeOptions,
): SseHandle {
  let lastSeenId = opts?.initialLastId ?? 'history';
  let attempt = 0;
  let closedByUser = false;
  let es: EventSource | null = null;
  let reconnectTimer: number | null = null;
  let state: SseConnectionState = 'connecting';

  const setState = (next: SseConnectionState) => {
    state = next;
    try {
      opts?.onStateChange?.(next);
    } catch {
      // ignore consumer errors
    }
  };

  const closeInternal = () => {
    closedByUser = true;
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    try {
      es?.close();
    } catch {
      // ignore close errors
    }
    es = null;
    setState('closed');
  };

  const dispatchEntry = (entry: SseEntry) => {
    // 已经 close 之后，原生 EventSource 不会再触发事件；这里防御 close 与
    // handler 触发之间的竞态、以及测试替身可能保留 listeners 的情况。
    if (closedByUser) return;
    // job.terminated 是后端在 job 终态时主动下发的「控制信号」，
    // 用于让前端结束订阅；不向上层 onEntry 透传，避免污染日志展示。
    if (entry.payload.event === 'job.terminated') {
      closeInternal();
      return;
    }
    onEntry(entry);
  };

  const handler = (kind: SseEvent['event']) => (e: MessageEvent<string>) => {
    try {
      const payload = JSON.parse(e.data) as Record<string, unknown>;
      const id = e.lastEventId || `${Date.now()}`;
      lastSeenId = id;
      dispatchEntry({
        id,
        receivedAt: new Date().toISOString(),
        payload: { ...(payload as object), event: kind } as SseEvent,
      });
    } catch (err) {
      console.warn('[sse] parse failed', err, e.data);
    }
  };

  const connect = () => {
    if (closedByUser) return;
    setState(attempt === 0 ? 'connecting' : 'reconnecting');
    const url = `${API_BASE}/jobs/${jobId}/events?last_id=${encodeURIComponent(lastSeenId)}`;
    es = new EventSource(url);

    es.onopen = () => {
      attempt = 0;
      setState('open');
    };

    for (const kind of KNOWN_EVENTS) {
      es.addEventListener(kind, handler(kind) as (e: MessageEvent<string>) => void);
    }

    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as Record<string, unknown>;
        const kind = (payload as { event?: SseEvent['event'] }).event;
        if (kind && (KNOWN_EVENTS as readonly string[]).includes(kind)) {
          const id = e.lastEventId || `${Date.now()}`;
          lastSeenId = id;
          dispatchEntry({
            id,
            receivedAt: new Date().toISOString(),
            payload: payload as unknown as SseEvent,
          });
        }
      } catch (err) {
        console.warn('[sse] parse failed', err, e.data);
      }
    };

    es.onerror = () => {
      // EventSource 默认会自动重连，但浏览器实现不一致：
      // - Chrome 会持续 retry 但用空 last-event-id；
      // - 服务端临时 5xx / 网络抖动后我们想用「最近 lastSeenId」续推，
      //   所以这里直接关掉，自己控制 backoff 与 last_id。
      const wasConnected = state === 'open';
      try {
        es?.close();
      } catch {
        // ignore close errors
      }
      es = null;
      if (closedByUser) return;
      if (attempt >= MAX_RETRY) {
        console.warn('[sse] max retries reached, giving up');
        setState('closed');
        return;
      }
      const delay = BACKOFF_SCHEDULE[Math.min(attempt, BACKOFF_SCHEDULE.length - 1)];
      attempt += 1;
      setState('reconnecting');
      if (wasConnected) {
        console.warn('[sse] disconnected, will reconnect in', delay, 'ms');
      }
      reconnectTimer = window.setTimeout(connect, delay);
    };
  };

  connect();

  return {
    close: closeInternal,
    getState: () => state,
  };
}
