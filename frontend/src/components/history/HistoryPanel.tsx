import { useMemo, useState } from 'react';
import {
  App,
  Button,
  Card,
  DatePicker,
  Pagination,
  Popconfirm,
  Space,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  DeleteOutlined,
  FolderOpenOutlined,
  ReloadOutlined,
  RedoOutlined,
} from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';
import { notifyError } from '@/api/messages';
import type { JobRead, Template } from '@/api/types';
import EmptyHint from '@/components/common/EmptyHint';
import { useConfigStore } from '@/store/configStore';
import { useJobStore } from '@/store/jobStore';
import { useWorkbenchStore } from '@/store/workbenchStore';

const { Text } = Typography;

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  queued: { color: 'default', label: '排队' },
  running: { color: 'processing', label: '生成中' },
  succeeded: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
  cancelled: { color: 'warning', label: '已取消' },
};

const PAGE_SIZE = 5;

interface JobCardProps {
  job: JobRead;
  templateName: string | undefined;
  onReopen: (job: JobRead) => void;
  onRetry: (job: JobRead) => void;
  onDelete: (job: JobRead) => void;
  pendingId: number | null;
}

function JobCard({ job, templateName, onReopen, onRetry, onDelete, pendingId }: JobCardProps) {
  const tag = STATUS_TAG[job.status] ?? { color: 'default', label: job.status };
  const time = dayjs(job.created_at).format('YYYY-MM-DD HH:mm');
  const isPending = pendingId === job.id;

  return (
    <Card size="small" className="history-card">
      <div className="history-card__head">
        <Space size={6}>
          <Text strong style={{ fontSize: 13 }}>
            #{job.id}
          </Text>
          <Tag color={tag.color} style={{ marginInlineEnd: 0 }}>
            {tag.label}
          </Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {time}
          </Text>
        </Space>
        <Space size={4} className="history-card__actions">
          <Tooltip title="重新打开（回填模板/提示词/输出目录，并加载候选图）">
            <Button
              size="small"
              icon={<FolderOpenOutlined />}
              onClick={() => onReopen(job)}
              loading={isPending}
            >
              重新打开
            </Button>
          </Tooltip>
          <Tooltip title="重新生成失败的候选（保留已成功的）">
            <Button
              size="small"
              icon={<RedoOutlined />}
              onClick={() => onRetry(job)}
              disabled={job.failed_count === 0}
            >
              重试整批
            </Button>
          </Tooltip>
          <Popconfirm
            title="删除该历史任务？"
            description="将同时删除 outputs/<job_id>/ 目录与所有候选记录"
            okText="删除"
            cancelText="取消"
            onConfirm={() => onDelete(job)}
            disabled={job.status === 'queued' || job.status === 'running'}
          >
            <Tooltip
              title={
                job.status === 'queued' || job.status === 'running'
                  ? '任务进行中，请先取消'
                  : ''
              }
            >
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={job.status === 'queued' || job.status === 'running'}
              >
                删除
              </Button>
            </Tooltip>
          </Popconfirm>
        </Space>
      </div>
      <div className="history-card__body">
        <Text className="history-card__template">{templateName ?? job.template_code}</Text>
        <Text className="history-card__prompt" type="secondary">
          {job.prompt || '（无提示词）'}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          成功 <Text strong>{job.succeeded_count}</Text> / 失败{' '}
          <Text strong>{job.failed_count}</Text> / 共{' '}
          <Text strong>{job.total_candidates}</Text>
        </Text>
      </div>
    </Card>
  );
}

export default function HistoryPanel() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [activeTpl, setActiveTpl] = useState<string>('__all__');
  const [page, setPage] = useState(1);
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);

  const templatesQuery = useQuery({
    queryKey: ['templates'],
    queryFn: endpoints.templates.list,
  });
  const templates = useMemo<Template[]>(() => templatesQuery.data ?? [], [templatesQuery.data]);

  const filter = useMemo(
    () => ({
      template_code: activeTpl === '__all__' ? undefined : activeTpl,
      created_after: range ? range[0].toISOString() : undefined,
      created_before: range ? range[1].toISOString() : undefined,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    }),
    [activeTpl, range, page],
  );

  const listQuery = useQuery({
    queryKey: ['jobs', filter],
    queryFn: () => endpoints.jobs.list(filter),
  });

  const setTemplateCode = useWorkbenchStore((s) => s.setTemplateCode);
  const setPrompt = useWorkbenchStore((s) => s.setPrompt);
  const {
    setSelectedProfileId,
    setSelectedSize,
    setOutputDir,
    setCandidatesPerImage,
    setAutoRetry,
    setRetryMax,
  } = useConfigStore();
  const setCurrentJob = useJobStore((s) => s.setCurrentJob);
  const setCurrentDetail = useJobStore((s) => s.setCurrentDetail);
  const resetJob = useJobStore((s) => s.reset);

  const reopenMutation = useMutation({
    mutationFn: (id: number) => endpoints.jobs.get(id),
    onSuccess: (detail) => {
      setTemplateCode(detail.template_code);
      setPrompt(detail.prompt);
      setSelectedProfileId(detail.api_profile_id);
      setSelectedSize(detail.size);
      setOutputDir(detail.output_dir);
      setCandidatesPerImage(detail.candidates_per_image);
      setAutoRetry(detail.auto_retry);
      setRetryMax(detail.retry_max);
      setCurrentDetail(detail);
      setCurrentJob({
        id: detail.id,
        template_code: detail.template_code,
        api_profile_id: detail.api_profile_id,
        model: detail.model,
        size: detail.size,
        prompt: detail.prompt,
        candidates_per_image: detail.candidates_per_image,
        auto_retry: detail.auto_retry,
        retry_max: detail.retry_max,
        output_dir: detail.output_dir,
        status: detail.status,
        total_candidates: detail.total_candidates,
        succeeded_count: detail.succeeded_count,
        failed_count: detail.failed_count,
        last_error: detail.last_error,
        created_at: detail.created_at,
        updated_at: detail.updated_at,
      });
      message.success(`已重新打开任务 #${detail.id}`);
    },
    onError: (err) => {
      notifyError(message, err);
    },
  });

  const retryMutation = useMutation({
    mutationFn: (id: number) => endpoints.jobs.retryFailed(id),
    onSuccess: (job) => {
      setCurrentJob(job);
      message.success(`已重新派发失败的候选：#${job.id}`);
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      void queryClient.invalidateQueries({ queryKey: ['job-detail', job.id] });
    },
    onError: (err) => {
      notifyError(message, err);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => endpoints.jobs.remove(id),
    onSuccess: (_, id) => {
      // 如果删的是当前 currentJob，把 jobStore 重置
      if (useJobStore.getState().currentJob?.id === id) {
        resetJob();
      }
      message.success('已删除');
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
    onError: (err) => {
      notifyError(message, err);
    },
  });

  const tabs = useMemo(() => {
    const items = [{ key: '__all__', label: '全部' }];
    for (const t of templates) items.push({ key: t.code, label: t.name });
    return items;
  }, [templates]);

  const data = listQuery.data;
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <Card
      size="small"
      className="workbench-card"
      title={<span>历史记录</span>}
      extra={
        <Space size={6}>
          <DatePicker.RangePicker
            size="small"
            allowClear
            value={range ?? undefined}
            onChange={(v) => {
              setPage(1);
              if (v && v[0] && v[1]) setRange([v[0], v[1]]);
              else setRange(null);
            }}
            placeholder={['起始', '结束']}
          />
          <Tooltip title="刷新">
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => {
                void queryClient.invalidateQueries({ queryKey: ['jobs'] });
              }}
            />
          </Tooltip>
        </Space>
      }
    >
      <Tabs
        size="small"
        activeKey={activeTpl}
        onChange={(k) => {
          setActiveTpl(k);
          setPage(1);
        }}
        items={tabs}
        style={{ marginBottom: 8 }}
      />

      {items.length === 0 ? (
        <EmptyHint title={listQuery.isLoading ? '加载中…' : '暂无历史任务'} />
      ) : (
        <div className="history-list">
          {items.map((job) => {
            const tpl = templates.find((t) => t.code === job.template_code);
            return (
              <JobCard
                key={job.id}
                job={job}
                templateName={tpl?.name}
                onReopen={(j) => reopenMutation.mutate(j.id)}
                onRetry={(j) => retryMutation.mutate(j.id)}
                onDelete={(j) => deleteMutation.mutate(j.id)}
                pendingId={
                  reopenMutation.isPending ? (reopenMutation.variables ?? null) : null
                }
              />
            );
          })}
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="history-pager">
          <Pagination
            size="small"
            current={page}
            pageSize={PAGE_SIZE}
            total={total}
            showSizeChanger={false}
            onChange={setPage}
          />
        </div>
      )}
    </Card>
  );
}
