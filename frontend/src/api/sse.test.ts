import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  subscribeJobEvents,
  type SseConnectionState,
  type SseEntry,
} from '@/api/sse';

/**
 * 极简 EventSource 替身，用于驱动 sse.ts 中的事件分发逻辑。
 * 仅实现 subscribeJobEvents 用到的字段：
 * - onopen / onerror（属性赋值）
 * - addEventListener('xxx', ...) （命名事件）
 * - close()
 * 并暴露 fireXxx() 方法供测试主动触发。
 */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  readyState = 0;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  private listeners = new Map<string, Array<(ev: MessageEvent) => void>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (ev: MessageEvent) => void): void {
    const arr = this.listeners.get(type) ?? [];
    arr.push(handler);
    this.listeners.set(type, arr);
  }

  close(): void {
    this.readyState = 2;
  }

  fireOpen(): void {
    this.readyState = 1;
    this.onopen?.(new Event('open'));
  }

  fireNamedEvent(type: string, data: unknown, lastEventId = ''): void {
    const arr = this.listeners.get(type) ?? [];
    const ev = new MessageEvent('message', {
      data: JSON.stringify(data),
      lastEventId,
    });
    for (const h of arr) h(ev);
  }
}

describe('subscribeJobEvents', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    (globalThis as unknown as { EventSource: typeof FakeEventSource }).EventSource =
      FakeEventSource;
  });

  afterEach(() => {
    delete (globalThis as unknown as { EventSource?: typeof FakeEventSource }).EventSource;
  });

  it('closes subscription on job.terminated and suppresses upstream forwarding', () => {
    const states: SseConnectionState[] = [];
    const entries: SseEntry[] = [];

    const handle = subscribeJobEvents(1, (e) => entries.push(e), {
      onStateChange: (s) => states.push(s),
    });
    expect(FakeEventSource.instances).toHaveLength(1);
    const es = FakeEventSource.instances[0];

    es.fireOpen();
    expect(handle.getState()).toBe('open');

    es.fireNamedEvent(
      'job.updated',
      { event: 'job.updated', job_id: 1, status: 'running', succeeded: 0, failed: 0, total: 2 },
      '1-0',
    );
    expect(entries).toHaveLength(1);
    expect(entries[0].payload.event).toBe('job.updated');

    es.fireNamedEvent(
      'job.terminated',
      { event: 'job.terminated', job_id: 1, status: 'failed', succeeded: 0, failed: 2, total: 2 },
      '1-1',
    );
    expect(entries).toHaveLength(1);
    expect(handle.getState()).toBe('closed');
    expect(es.readyState).toBe(2);
    expect(states[states.length - 1]).toBe('closed');

    es.fireNamedEvent(
      'job.updated',
      { event: 'job.updated', job_id: 1, status: 'failed', succeeded: 0, failed: 2, total: 2 },
      '1-2',
    );
    expect(entries).toHaveLength(1);
  });

  it('user-initiated close() finalises state and stops the EventSource', () => {
    const handle = subscribeJobEvents(2, () => {});
    const es = FakeEventSource.instances[0];
    es.fireOpen();
    expect(handle.getState()).toBe('open');

    handle.close();
    expect(handle.getState()).toBe('closed');
    expect(es.readyState).toBe(2);
  });

  it('forwards normal candidate events untouched', () => {
    const entries: SseEntry[] = [];
    subscribeJobEvents(3, (e) => entries.push(e));
    const es = FakeEventSource.instances[0];
    es.fireOpen();

    es.fireNamedEvent(
      'candidate.running',
      {
        event: 'candidate.running',
        candidate_id: 9,
        item_id: 2,
        index: 0,
        attempt: 1,
        source_name: 'a.png',
      },
      '3-0',
    );

    expect(entries).toHaveLength(1);
    expect(entries[0].payload.event).toBe('candidate.running');
  });
});
