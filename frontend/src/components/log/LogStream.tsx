import { useEffect, useMemo, useRef } from 'react';
import { Button, Card, Empty, Space, Tag, Tooltip, Typography } from 'antd';
import { ClearOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { subscribeJobEvents, type SseEntry, type SseEvent } from '@/api/sse';
import { useJobStore } from '@/store/jobStore';

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

  // 订阅 / 取消 SSE
  useEffect(() => {
    if (!currentJob) return;
    const handle = subscribeJobEvents(currentJob.id, (entry: SseEntry) => {
      // 过滤心跳
      if (entry.payload.event === 'ping') return;
      appendEvent(entry);
    });
    return () => handle.close();
  }, [currentJob, appendEvent]);

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
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <Text style={{ color: '#94a3b8', fontSize: 12 }}>
                  {currentJob ? '等待 worker 上报第一条事件…' : '提交任务后这里会实时显示生成进展'}
                </Text>
              }
            />
          </div>
        ) : (
          events.map((e) => {
            const ts = dayjs(e.receivedAt).format('HH:mm:ss.SSS');
            const color = LEVEL_COLOR[e.payload.event] ?? 'default';
            return (
              <div key={e.id} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
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
