import { create } from 'zustand';
import type { SseEntry, SseEvent } from '@/api/sse';
import type { JobCandidateRead, JobDetail, JobRead } from '@/api/types';

const MAX_LOG = 500;

interface JobState {
  currentJob: JobRead | null;
  currentDetail: JobDetail | null;
  /** 经 SSE 收到的事件序列（按时间正序） */
  events: SseEntry[];
  setCurrentJob: (j: JobRead | null) => void;
  setCurrentDetail: (d: JobDetail | null) => void;
  patchCandidate: (
    itemId: number,
    candidateId: number,
    partial: Partial<JobCandidateRead>,
  ) => void;
  appendEvent: (e: SseEntry) => void;
  resetEvents: () => void;
  reset: () => void;
}

function _patchDetailCandidate(
  detail: JobDetail | null,
  itemId: number,
  candidateId: number,
  partial: Partial<JobCandidateRead>,
): JobDetail | null {
  if (!detail) return detail;
  let touched = false;
  const items = detail.items.map((it) => {
    if (it.id !== itemId) return it;
    const candidates = it.candidates.map((c) => {
      if (c.id !== candidateId) return c;
      touched = true;
      return { ...c, ...partial };
    });
    return touched ? { ...it, candidates } : it;
  });
  return touched ? { ...detail, items } : detail;
}

function _applyMutualExclusion(
  detail: JobDetail | null,
  itemId: number,
  selectedId: number,
): JobDetail | null {
  if (!detail) return detail;
  let touched = false;
  const items = detail.items.map((it) => {
    if (it.id !== itemId) return it;
    const candidates = it.candidates.map((c) => {
      const next = c.id === selectedId;
      if (c.is_selected === next) return c;
      touched = true;
      return { ...c, is_selected: next };
    });
    return touched ? { ...it, candidates } : it;
  });
  return touched ? { ...detail, items } : detail;
}

function _reduceSseEventToDetail(
  detail: JobDetail | null,
  payload: SseEvent,
): JobDetail | null {
  switch (payload.event) {
    case 'candidate.running':
      return _patchDetailCandidate(detail, payload.item_id, payload.candidate_id, {
        status: 'running',
        attempts: payload.attempt,
      });
    case 'candidate.retry':
      return _patchDetailCandidate(detail, payload.item_id, payload.candidate_id, {
        status: 'running',
        attempts: payload.attempt,
        last_error: payload.error,
      });
    case 'candidate.succeeded':
      return _patchDetailCandidate(detail, payload.item_id, payload.candidate_id, {
        status: 'succeeded',
        output_path: payload.output_path,
        last_error: null,
      });
    case 'candidate.failed':
      return _patchDetailCandidate(detail, payload.item_id, payload.candidate_id, {
        status: 'failed',
        attempts: payload.attempt,
        last_error: payload.error,
      });
    case 'candidate.selected':
      return payload.is_selected
        ? _applyMutualExclusion(detail, payload.item_id, payload.candidate_id)
        : _patchDetailCandidate(detail, payload.item_id, payload.candidate_id, {
            is_selected: false,
          });
    default:
      return detail;
  }
}

export const useJobStore = create<JobState>((set, get) => ({
  currentJob: null,
  currentDetail: null,
  events: [],
  setCurrentJob: (j) => {
    const prev = get().currentJob;
    if (prev && j && prev.id !== j.id) {
      set({ currentJob: j, currentDetail: null, events: [] });
    } else if (!j) {
      set({ currentJob: null });
    } else {
      set({ currentJob: j });
    }
  },
  setCurrentDetail: (d) => set({ currentDetail: d }),
  patchCandidate: (itemId, candidateId, partial) => {
    const cur = get().currentDetail;
    const next = _patchDetailCandidate(cur, itemId, candidateId, partial);
    if (next !== cur) set({ currentDetail: next });
  },
  appendEvent: (e) => {
    const eventJobId = 'job_id' in e.payload ? e.payload.job_id : null;
    const activeJobId = get().currentJob?.id ?? null;
    if (eventJobId != null && activeJobId != null && eventJobId !== activeJobId) {
      return;
    }

    const next = get().events.concat(e);
    if (next.length > MAX_LOG) {
      next.splice(0, next.length - MAX_LOG);
    }
    set({ events: next });

    if (e.payload.event === 'job.updated') {
      const cur = get().currentJob;
      if (cur && cur.id === e.payload.job_id) {
        set({
          currentJob: {
            ...cur,
            status: e.payload.status as JobRead['status'],
            succeeded_count: e.payload.succeeded,
            failed_count: e.payload.failed,
            total_candidates: e.payload.total,
          },
        });
      }
      return;
    }

    const curDetail = get().currentDetail;
    const nextDetail = _reduceSseEventToDetail(curDetail, e.payload);
    if (nextDetail !== curDetail) set({ currentDetail: nextDetail });
  },
  resetEvents: () => set({ events: [] }),
  reset: () => set({ currentJob: null, currentDetail: null, events: [] }),
}));
