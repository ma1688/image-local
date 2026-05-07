import { useMemo } from 'react';
import {
  App,
  Button,
  Card,
  Empty,
  Radio,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  CloseCircleOutlined,
  DownloadOutlined,
  LoadingOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { endpoints } from '@/api/endpoints';
import type { JobCandidateRead, JobItemRead } from '@/api/types';
import { useJobStore } from '@/store/jobStore';

const { Text } = Typography;

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  queued: { color: 'default', label: '排队' },
  running: { color: 'processing', label: '生成中' },
  succeeded: { color: 'success', label: '成功' },
  failed: { color: 'error', label: '失败' },
  cancelled: { color: 'warning', label: '取消' },
};

function thumbUrl(absPath: string): string {
  return `/api/files?path=${encodeURIComponent(absPath)}`;
}

interface CandidateCardProps {
  candidate: JobCandidateRead;
  jobId: number;
  onSelect: (candidateId: number, next: boolean) => void;
  pending: boolean;
}

function CandidateCard({ candidate, onSelect, pending }: CandidateCardProps) {
  const tag = STATUS_TAG[candidate.status] ?? { color: 'default', label: candidate.status };
  const canSelect = candidate.status === 'succeeded';

  return (
    <div className="result-candidate">
      <div className="result-candidate__thumb">
        {candidate.status === 'succeeded' && candidate.output_path ? (
          <img src={thumbUrl(candidate.output_path)} alt={`候选 ${candidate.index}`} />
        ) : candidate.status === 'failed' ? (
          <Tooltip title={candidate.last_error ?? ''}>
            <CloseCircleOutlined className="result-candidate__failed-icon" />
          </Tooltip>
        ) : candidate.status === 'cancelled' ? (
          <Tooltip title="任务已取消，本候选未生成">
            <StopOutlined className="result-candidate__cancelled-icon" />
          </Tooltip>
        ) : (
          <Spin indicator={<LoadingOutlined spin style={{ fontSize: 18 }} />} />
        )}
      </div>
      <div className="result-candidate__meta">
        <Space size={6}>
          <Text strong style={{ fontSize: 12 }}>
            候选 {candidate.index}
          </Text>
          <Tag color={tag.color} style={{ marginInlineEnd: 0, fontSize: 10 }}>
            {tag.label}
          </Tag>
        </Space>
        <Tooltip title={canSelect ? '' : '只有生成成功的候选可被选为最终结果'}>
          <Radio
            disabled={!canSelect || pending}
            checked={candidate.is_selected}
            onClick={() => {
              onSelect(candidate.id, !candidate.is_selected);
            }}
          >
            <Text style={{ fontSize: 12 }}>设为选中</Text>
          </Radio>
        </Tooltip>
      </div>
    </div>
  );
}

interface ResultRowProps {
  item: JobItemRead;
  jobId: number;
  onSelect: (candidateId: number, next: boolean) => void;
  pendingId: number | null;
}

function ResultRow({ item, jobId, onSelect, pendingId }: ResultRowProps) {
  return (
    <div className="result-row">
      <div className="result-row__source">
        <div className="result-row__source-thumb">
          <img src={thumbUrl(item.source_path)} alt={item.source_name} />
        </div>
        <div>
          <Text strong style={{ fontSize: 13 }}>
            {item.source_name}
          </Text>
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              #{item.id}
            </Text>
          </div>
        </div>
      </div>
      <div className="result-row__candidates">
        {item.candidates.map((c) => (
          <CandidateCard
            key={c.id}
            candidate={c}
            jobId={jobId}
            onSelect={onSelect}
            pending={pendingId === c.id}
          />
        ))}
      </div>
    </div>
  );
}

export default function ResultsList() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const detail = useJobStore((s) => s.currentDetail);
  const patchCandidate = useJobStore((s) => s.patchCandidate);

  const stats = useMemo(() => {
    if (!detail) return null;
    const all = detail.items.flatMap((i) => i.candidates);
    const selected = all.filter((c) => c.is_selected).length;
    return {
      succeeded: all.filter((c) => c.status === 'succeeded').length,
      total: all.length,
      selected,
    };
  }, [detail]);

  const selectMutation = useMutation({
    mutationFn: ({
      jobId,
      candidateId,
      next,
    }: {
      jobId: number;
      candidateId: number;
      next: boolean;
      itemId: number;
    }) => endpoints.jobs.selectCandidate(jobId, candidateId, { is_selected: next }),
    onMutate: ({ candidateId, next, itemId }) => {
      // 乐观更新：把同 item 其他候选 is_selected 设为 false（互斥）；当前候选设 next
      const prev = useJobStore.getState().currentDetail;
      if (!prev) return;
      if (next) {
        const items = prev.items.map((it) => {
          if (it.id !== itemId) return it;
          return {
            ...it,
            candidates: it.candidates.map((c) => ({
              ...c,
              is_selected: c.id === candidateId,
            })),
          };
        });
        useJobStore.setState({ currentDetail: { ...prev, items } });
      } else {
        patchCandidate(itemId, candidateId, { is_selected: false });
      }
    },
    onError: (err) => {
      message.error(err instanceof ApiError ? err.detail : '设置失败');
      void queryClient.invalidateQueries({ queryKey: ['job-detail'] });
    },
  });

  if (!detail || detail.items.length === 0) {
    return (
      <Card size="small" className="workbench-card" title="生成结果">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <Text type="secondary" style={{ fontSize: 12 }}>
              尚无结果，点击「开始生成」后这里将按行显示候选图
            </Text>
          }
          style={{ padding: '24px 0' }}
        />
      </Card>
    );
  }

  const downloadAll = () => {
    if (!detail) return;
    if (!stats || stats.succeeded === 0) {
      message.info('当前没有已成功的候选可下载');
      return;
    }
    window.location.href = endpoints.jobs.downloadUrl(detail.id, 'all');
  };

  const downloadSelected = () => {
    if (!detail) return;
    if (!stats || stats.selected === 0) {
      message.info('请先勾选至少一个候选作为最终结果');
      return;
    }
    window.location.href = endpoints.jobs.downloadUrl(detail.id, 'selected');
  };

  return (
    <Card
      size="small"
      className="workbench-card"
      title={
        <Space>
          <span>生成结果</span>
          {stats && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              成功 {stats.succeeded} / 总 {stats.total} · 已选 {stats.selected}
            </Text>
          )}
        </Space>
      }
      extra={
        <Space size={8}>
          <Button icon={<DownloadOutlined />} onClick={downloadAll} size="small">
            下载全部
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={downloadSelected}
            type="primary"
            size="small"
          >
            下载选中
          </Button>
        </Space>
      }
    >
      <div className="result-list">
        {detail.items.map((it) => (
          <ResultRow
            key={it.id}
            item={it}
            jobId={detail.id}
            onSelect={(cid, next) =>
              selectMutation.mutate({
                jobId: detail.id,
                candidateId: cid,
                next,
                itemId: it.id,
              })
            }
            pendingId={selectMutation.isPending ? (selectMutation.variables?.candidateId ?? null) : null}
          />
        ))}
      </div>
    </Card>
  );
}
