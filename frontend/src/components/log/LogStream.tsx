import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, Space, Tag, Tooltip, Typography } from 'antd';
import { ClearOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  subscribeJobEvents,
  type SseConnectionState,
  type SseEntry,
  type SseEvent,
} from '@/api/sse';
import EmptyHint from '@/components/common/EmptyHint';
import { useJobStore } from '@/store/jobStore';
import { isTerminalStatus } from '@/store/jobStateHelpers';

const { Text } = Typography;

const LEVEL_COLOR: Record<string, string> = {
  'job.created': 'blue',
  'job.updated': 'cyan',
  'candidate.running': 'gold',
  'candidate.retry': 'orange',
  'candidate.succeeded': 'green',
  'candidate.failed': 'red',
  error: 'red',
};

function formatLine(p: SseEvent): string {
  switch (p.event) {
    case 'job.created':
      return `[系统] 任务 #${p.job_id} 已创建，共 ${p.total} 候选（${p.items.length} 张 × ${p.candidates_per_image}）`;
    case 'job.updated':
      return `[聚合] 状态=${p.status} 成功=${p.succeeded} 失败=${p.failed} 总=${p.total}`;
    case 'candidate.running':
      return `[开始] ${p.source_name} 候选 ${p.index}（尝试 ${p.attempt}）`;
    case 'candidate.retry':
      return `[重试] ${p.source_name} 候选 ${p.index}（尝试 ${p.attempt}）原因: ${p.error}`;
    case 'candidate.succeeded':
      return `[成功] ${p.source_name} 候选 ${p.index} → ${p.output_path}`;
    case 'candidate.failed':
      return `[失败] ${p.source_name} 候选 ${p.index}（尝试 ${p.attempt}）原因: ${p.error}`;
    case 'error':
      return `[错误] ${p.message}`;
    default:
      return JSON.stringify(p);
  }
}

export default function LogStream() {
  const currentJob = useJobStore((s) => s.currentJob);
  const events = useJobStore((s) => s.events);
  const appendEvent = useJobStore((s) => s.appendEvent);
  const resetEvents = useJobStore((s) => s.resetEvents);

  const containerRef = useRef<HTMLDivElement>(null);
  const [sseState, setSseState] = useState<SseConnectionState>('closed');

  // 订阅 / 取消 SSE
  //
  // 依赖项里加上 currentJob.status 是为了 retry 场景：
  // 1. job 进入终态时后端会发 job.terminated，sse.ts 收到后内部 close 订阅；
  //    此时 sseState 已是 'closed'，但订阅 handle 仍未释放。
  // 2. 用户点击 retry，HistoryPanel 在 mutation onSuccess 中调用
  //    setCurrentJob(newJob)，新 job.status 从 failed/cancelled 变为 running；
  //    依赖 status 后本 useEffect 重新执行 → cleanup 旧 handle → 重新订阅。
  // 3. 仅依赖 currentJob 整个对象会让任何字段变化（例如 succeeded_count 推进）
  //    都触发重订阅，过于浪费；只关注 id + status 两个真正影响订阅生命周期的字段。
  const jobId = currentJob?.id ?? null;
  const jobStatus = currentJob?.status ?? null;
  useEffect(() => {
    if (jobId == null) return;
    if (isTerminalStatus(jobStatus)) {
      setSseState('closed');
      return;
    }
    const handle = subscribeJobEvents(
      jobId,
      (entry: SseEntry) => {
        if (entry.payload.event === 'ping') return;
        appendEvent(entry);
      },
      { onStateChange: setSseState },
    );
    return () => handle.close();
  }, [jobId, jobStatus, appendEvent]);

  // 自动滚动到底
  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  const status = currentJob?.status ?? null;

  const subtitle = useMemo(() => {
    if (!currentJob) return '尚未提交任务';
    return `Job #${currentJob.id}`;
  }, [currentJob]);

  return (
    <Card
      size="small"
      className="workbench-card log-card"
      title={
        <Space>
          <span>运行日志</span>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {subtitle}
          </Text>
          {status && <Tag color={status === 'running' ? 'processing' : 'default'}>{status}</Tag>}
          {currentJob && sseState !== 'open' && sseState !== 'closed' && (
            <Tooltip title="网络抖动或后端重启时会自动重连，并按 Last-Event-ID 续推未消费事件">
              <Tag color="orange" style={{ marginInlineEnd: 0 }}>
                {sseState === 'connecting' ? '连接中…' : '重连中…'}
              </Tag>
            </Tooltip>
          )}
        </Space>
      }
      extra={
        <Tooltip title="清空当前日志">
          <Button size="small" icon={<ClearOutlined />} onClick={resetEvents}>
            清空日志
          </Button>
        </Tooltip>
      }
      styles={{ body: { padding: 0 } }}
    >
      <div
        ref={containerRef}
        style={{
          height: 'clamp(420px, calc(100vh - 280px), 760px)',
          overflowY: 'auto',
          padding: '8px 12px',
          background: '#0b1220',
          color: '#e2e8f0',
          fontFamily:
            "ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', 'Roboto Mono', monospace",
          fontSize: 12,
          lineHeight: '18px',
        }}
      >
        {events.length === 0 ? (
          <div
            style={{
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <EmptyHint
              description={
                <Text style={{ color: '#94a3b8', fontSize: 12 }}>
                  {currentJob
                    ? '等待 worker 上报第一条事件…'
                    : '提交任务后这里会实时显示生成进展'}
                </Text>
              }
            />
          </div>
        ) : (
          events.map((e, idx) => {
            const ts = dayjs(e.receivedAt).format('HH:mm:ss.SSS');
            const color = LEVEL_COLOR[e.payload.event] ?? 'default';
            // 仅最近一条条目挂上高亮动画 className，其余按静态样式渲染。
            // 配合 CSS 关键帧实现淡入 + 1s 内黄色高亮渐隐。
            const isLatest = idx === events.length - 1;
            return (
              <div
                key={e.id}
                className={isLatest ? 'log-line log-line--new' : 'log-line'}
              >
                <span style={{ color: '#64748b', whiteSpace: 'nowrap' }}>{ts}</span>
                <Tag color={color} style={{ marginInlineEnd: 0, fontSize: 10, lineHeight: '16px' }}>
                  {e.payload.event}
                </Tag>
                <span style={{ flex: 1, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {formatLine(e.payload)}
                </span>
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}
