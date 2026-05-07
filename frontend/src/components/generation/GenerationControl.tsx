import { useEffect, useRef } from 'react';
import { App, Button, Card, Col, InputNumber, Row, Space, Switch, Tag, Tooltip, Typography } from 'antd';
import { PlayCircleOutlined, ClearOutlined, StopOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';
import { notifyError } from '@/api/messages';
import type { JobCreate } from '@/api/types';
import { useConfigStore } from '@/store/configStore';
import { useImageSourceStore } from '@/store/imageSourceStore';
import { useJobStore } from '@/store/jobStore';
import { TERMINAL_JOB_STATUSES, shouldApplyPolledDetail } from '@/store/jobStateHelpers';
import { useWorkbenchStore } from '@/store/workbenchStore';

const { Text } = Typography;

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  queued: { color: 'default', label: '排队中' },
  running: { color: 'processing', label: '生成中' },
  succeeded: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '已失败' },
  cancelled: { color: 'warning', label: '已取消' },
};

export default function GenerationControl() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();

  const {
    candidatesPerImage,
    retryMax,
    autoRetry,
    outputDir,
    selectedProfileId,
    selectedModel,
    selectedSize,
    setCandidatesPerImage,
    setRetryMax,
    setAutoRetry,
    setOutputDir,
  } = useConfigStore();

  const selected = useImageSourceStore((s) => s.selected);
  const items = useImageSourceStore((s) => s.items);
  const clearAll = useImageSourceStore((s) => s.clearAll);

  const { templateCode, prompt } = useWorkbenchStore();

  const { currentJob, setCurrentJob, setCurrentDetail, reset: resetJob } = useJobStore();

  const selectedCount = selected.size;
  const totalCandidates = selectedCount * candidatesPerImage;

  // 提交后轮询 job 详情。
  // enabled 排除所有终态（succeeded/failed/cancelled）：终态后由 SSE 写入的
  // detail 是权威，不再额外发 polling 请求，避免 stale 数据回写覆盖。
  const detailQuery = useQuery({
    queryKey: ['job-detail', currentJob?.id],
    queryFn: () => endpoints.jobs.get(currentJob!.id),
    enabled: !!currentJob && !TERMINAL_JOB_STATUSES.has(currentJob.status),
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return 1500;
      return data.status === 'queued' || data.status === 'running' ? 1500 : false;
    },
  });

  useEffect(() => {
    if (!detailQuery.data) return;
    const next = detailQuery.data;
    // 双保险：即便 enabled 切到 false 之前还有 in-flight refetch，
    // 这里也要丢弃显著 stale 的 polling 结果（store 已是终态而拉到的还在跑）。
    const cur = useJobStore.getState().currentJob;
    if (!shouldApplyPolledDetail(cur?.status, next.status)) return;
    setCurrentDetail(next);
    setCurrentJob({
      id: next.id,
      template_code: next.template_code,
      api_profile_id: next.api_profile_id,
      model: next.model,
      size: next.size,
      prompt: next.prompt,
      candidates_per_image: next.candidates_per_image,
      auto_retry: next.auto_retry,
      retry_max: next.retry_max,
      output_dir: next.output_dir,
      status: next.status,
      total_candidates: next.total_candidates,
      succeeded_count: next.succeeded_count,
      failed_count: next.failed_count,
      last_error: next.last_error,
      created_at: next.created_at,
      updated_at: next.updated_at,
    });
  }, [detailQuery.data, setCurrentDetail, setCurrentJob]);

  const submitMutation = useMutation({
    mutationFn: (payload: JobCreate) => endpoints.jobs.submit(payload),
    onSuccess: (job) => {
      setCurrentJob(job);
      message.success(`任务已提交：#${job.id}（${job.total_candidates} 候选）`);
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
    onError: (err) => {
      notifyError(message, err);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => endpoints.jobs.cancel(id),
    onSuccess: async (job) => {
      setCurrentJob(job);
      message.success('任务已请求取消（已排队的候选不再继续）');
      // useQuery 的 enabled 在 status==='cancelled' 时为 false，
      // 这里主动 fetch 一次最新 detail 直写 store，让 queued -> cancelled
      // 的候选在 ResultsList 中立刻可见。
      try {
        const fresh = await endpoints.jobs.get(job.id);
        setCurrentDetail(fresh);
      } catch (e) {
        // 拉取失败不阻塞 cancel 体验，SSE 仍会增量推送 running 候选完成事件
        console.warn('refresh detail after cancel failed', e);
      }
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
    onError: (err) => {
      notifyError(message, err);
    },
  });

  const onStart = () => {
    if (isRunning) return; // 已经在跑，不重复提交
    if (!selectedProfileId) return message.warning('请先选择 API 配置');
    if (!selectedModel) return message.warning('请先选择模型');
    if (selectedCount === 0) return message.warning('请先选择要处理的图片');

    const payload: JobCreate = {
      template_code: templateCode,
      api_profile_id: selectedProfileId,
      model: selectedModel,
      size: selectedSize,
      prompt,
      candidates_per_image: candidatesPerImage,
      auto_retry: autoRetry,
      retry_max: retryMax,
      output_dir: outputDir,
      source_paths: items.filter((i) => i.valid && selected.has(i.path)).map((i) => i.path),
    };
    submitMutation.mutate(payload);
  };

  const isRunning = currentJob && (currentJob.status === 'queued' || currentJob.status === 'running');
  const tagInfo = currentJob ? STATUS_TAG[currentJob.status] ?? { color: 'default', label: currentJob.status } : null;

  // 快捷键：Ctrl/Cmd + Enter -> 开始生成；Esc -> 取消运行中任务。
  // 用 ref 持有最新的 onStart / cancelMutation，避免每次 deps 变化都重新绑定 listener。
  const onStartRef = useRef<() => void>(() => {});
  const onCancelRef = useRef<() => void>(() => {});
  onStartRef.current = onStart;
  onCancelRef.current = () => {
    if (isRunning && currentJob) cancelMutation.mutate(currentJob.id);
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // 在 input/textarea/contenteditable 内只处理 Ctrl/Cmd+Enter，
      // 单独的 Enter 留给原生表单行为（避免误触发）。
      const target = e.target as HTMLElement | null;
      const inEditable =
        !!target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable);

      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        onStartRef.current();
        return;
      }
      if (e.key === 'Escape' && !inEditable) {
        e.preventDefault();
        onCancelRef.current();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <Card
      size="small"
      className="workbench-card generation-card"
      title={
        <Space>
          <span>生成控制</span>
          {currentJob && tagInfo && <Tag color={tagInfo.color}>{tagInfo.label}</Tag>}
          {currentJob && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              #{currentJob.id} · 成功 {currentJob.succeeded_count} / 失败 {currentJob.failed_count} /
              共 {currentJob.total_candidates}
            </Text>
          )}
        </Space>
      }
      styles={{ body: { paddingBottom: 12 } }}
    >
      <Row gutter={16} align="middle">
        <Col xs={24} xl={12}>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              每张生成数量
            </Text>
            <InputNumber
              min={1}
              max={6}
              value={candidatesPerImage}
              onChange={(v) => setCandidatesPerImage(v ?? 1)}
              disabled={!!isRunning}
              style={{ width: '100%' }}
            />
          </Space>
        </Col>
        <Col xs={24} xl={12}>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Tooltip title="生成失败时是否自动重新生成">
              <Text type="secondary" style={{ fontSize: 12 }}>
                失败后自动重新生成
              </Text>
            </Tooltip>
            <Switch checked={autoRetry} onChange={setAutoRetry} disabled={!!isRunning} />
          </Space>
        </Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 12 }} align="middle">
        <Col xs={24} xl={12}>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              失败重试次数（1-5）
            </Text>
            <InputNumber
              min={1}
              max={5}
              value={retryMax}
              onChange={(v) => setRetryMax(v ?? 1)}
              disabled={!autoRetry || !!isRunning}
              style={{ width: '100%' }}
            />
          </Space>
        </Col>
        <Col xs={24} xl={12}>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              输出目录
            </Text>
            <input
              value={outputDir}
              onChange={(e) => setOutputDir(e.target.value)}
              disabled={!!isRunning}
              style={{
                width: '100%',
                height: 32,
                border: '1px solid #d9d9d9',
                borderRadius: 6,
                padding: '4px 11px',
                fontSize: 14,
                background: isRunning ? '#fafafa' : '#fff',
              }}
            />
          </Space>
        </Col>
      </Row>

      <Row gutter={12} style={{ marginTop: 16 }}>
        <Col flex="auto">
          {isRunning ? (
            <Tooltip title="快捷键 Esc">
              <Button
                danger
                size="large"
                block
                icon={<StopOutlined />}
                onClick={() => currentJob && cancelMutation.mutate(currentJob.id)}
                loading={cancelMutation.isPending}
              >
                取消任务
              </Button>
            </Tooltip>
          ) : (
            <Tooltip title="快捷键 Ctrl/Cmd + Enter">
              <Button
                type="primary"
                size="large"
                block
                icon={<PlayCircleOutlined />}
                onClick={onStart}
                loading={submitMutation.isPending}
                disabled={selectedCount === 0 || items.length === 0}
              >
                {selectedCount === 0
                  ? '开始生成'
                  : `开始生成（${selectedCount} 张 × ${candidatesPerImage} = ${totalCandidates} 候选）`}
              </Button>
            </Tooltip>
          )}
        </Col>
        <Col flex="80px">
          <Button
            size="large"
            icon={<ClearOutlined />}
            block
            onClick={() => {
              clearAll();
              resetJob();
            }}
            disabled={!!isRunning}
          >
            清空
          </Button>
        </Col>
      </Row>
    </Card>
  );
}
