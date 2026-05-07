// 与后端 publish 出来的事件类型对齐
export type SseEvent =
  | { event: 'job.created'; job_id: number; total: number; candidates_per_image: number; items: { path: string; name: string }[] }
  | { event: 'job.updated'; job_id: number; status: string; succeeded: number; failed: number; total: number }
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

export interface SseHandle {
  close: () => void;
}

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';

const KNOWN_EVENTS = [
  'job.created',
  'job.updated',
  'candidate.running',
  'candidate.retry',
  'candidate.succeeded',
  'candidate.failed',
  'candidate.selected',
  'ping',
  'error',
] as const;

export function subscribeJobEvents(
  jobId: number,
  onEntry: (entry: SseEntry) => void,
  opts?: { lastId?: string },
): SseHandle {
  const lastId = opts?.lastId ?? 'history';
  const url = `${API_BASE}/jobs/${jobId}/events?last_id=${encodeURIComponent(lastId)}`;
  const es = new EventSource(url);

  const handler = (kind: SseEvent['event']) => (e: MessageEvent<string>) => {
    try {
      const payload = JSON.parse(e.data) as Record<string, unknown>;
      onEntry({
        id: e.lastEventId || `${Date.now()}`,
        receivedAt: new Date().toISOString(),
        payload: { ...(payload as object), event: kind } as SseEvent,
      });
    } catch (err) {
      console.warn('[sse] parse failed', err, e.data);
    }
  };

  for (const kind of KNOWN_EVENTS) {
    es.addEventListener(kind, handler(kind) as (e: MessageEvent<string>) => void);
  }

  // 默认 onmessage 兜底（无 event 字段）
  es.onmessage = (e) => {
    try {
      const payload = JSON.parse(e.data) as Record<string, unknown>;
      const kind = (payload as { event?: SseEvent['event'] }).event;
      if (kind && (KNOWN_EVENTS as readonly string[]).includes(kind)) {
        onEntry({
          id: e.lastEventId || `${Date.now()}`,
          receivedAt: new Date().toISOString(),
          payload: payload as unknown as SseEvent,
        });
      }
    } catch (err) {
      console.warn('[sse] parse failed', err, e.data);
    }
  };

  es.onerror = (err) => {
    console.warn('[sse] error', err);
  };

  return {
    close: () => es.close(),
  };
}
