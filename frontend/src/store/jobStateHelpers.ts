/**
 * Job 状态判定与 detail 写入策略 helpers。
 *
 * 背景：
 *   GenerationControl 通过 react-query 周期性轮询 detail（refetchInterval=1500ms）。
 *   SSE 也会增量更新 store.currentDetail。两者并行时，若 polling 在 SSE 已经把
 *   currentJob 推到终态（succeeded/failed/cancelled）之后才返回较旧的进行中数据，
 *   useEffect 直接 setCurrentDetail 会把 SSE 已写好的终态候选状态覆盖回 running。
 *   这里抽出小工具，让消费侧能够干净地丢弃这种 stale polling 数据。
 */

export const TERMINAL_JOB_STATUSES: ReadonlySet<string> = new Set([
  'succeeded',
  'failed',
  'cancelled',
]);

export function isTerminalStatus(s?: string | null): boolean {
  return !!s && TERMINAL_JOB_STATUSES.has(s);
}

/**
 * 是否应当用 polling 拿到的 detail 覆盖当前 store 中的 detail。
 *
 * 规则：当 store 已经认为 job 处于终态（多半由 SSE 推送写入），但 polling
 * 仍然返回非终态状态时，认为这次 polling 是 stale 的（in-flight 请求或
 * race condition），不要覆盖。其它情况一律应用。
 */
export function shouldApplyPolledDetail(
  currentStatus: string | null | undefined,
  nextStatus: string,
): boolean {
  if (isTerminalStatus(currentStatus) && !isTerminalStatus(nextStatus)) {
    return false;
  }
  return true;
}
