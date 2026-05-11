import { useEffect, useMemo, useRef, useState } from 'react';
import {
  App,
  Button,
  Checkbox,
  Input,
  InputNumber,
  Modal,
  Popover,
  Select,
  Space,
  Switch,
  Tooltip,
  Typography,
} from 'antd';
import {
  ApiOutlined,
  FolderOpenOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SlidersOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { endpoints } from '@/api/endpoints';
import { notifyError } from '@/api/messages';
import type { JobCreate, ModelInfo, Template } from '@/api/types';
import { useConfigStore } from '@/store/configStore';
import { useImageSourceStore } from '@/store/imageSourceStore';
import { useJobStore } from '@/store/jobStore';
import { TERMINAL_JOB_STATUSES, shouldApplyPolledDetail } from '@/store/jobStateHelpers';
import { useWorkbenchStore } from '@/store/workbenchStore';

const { Text } = Typography;
const PROMPT_MAX = 1000;
const SIZE_OPTIONS = ['512x512', '768x768', '1024x1024', '1024x1536', '1536x1024', '2048x2048'];

function stopPopoverClick(e: React.MouseEvent) {
  e.stopPropagation();
}

function compactPrompt(value: string) {
  const normalized = value.replace(/\s+/g, ' ').trim();
  return normalized || '描述图片改图目标，使用 {prompt} 填充模板；点击这里输入提示词';
}

export default function WorkflowBar() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const submittingRef = useRef(false);

  const {
    sourceType,
    lastScanDir,
    items,
    selected,
    setSourceType,
    setLastScanDir,
    setItems,
    selectAllValid,
  } = useImageSourceStore();

  const {
    selectedProfileId,
    selectedModel,
    selectedSize,
    candidatesPerImage,
    autoRetry,
    retryMax,
    outputDir,
    setSelectedProfileId,
    setSelectedModel,
    setSelectedSize,
    setCandidatesPerImage,
    setRetryMax,
    setAutoRetry,
    setOutputDir,
  } = useConfigStore();
  const { templateCode, setTemplateCode, prompt, setPrompt } = useWorkbenchStore();
  const { currentJob, setCurrentJob, setCurrentDetail } = useJobStore();

  const [scanModalOpen, setScanModalOpen] = useState(false);
  const [scanPath, setScanPath] = useState(lastScanDir);
  const [scanRecursive, setScanRecursive] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);

  const templatesQuery = useQuery({
    queryKey: ['templates'],
    queryFn: endpoints.templates.list,
  });
  const profilesQuery = useQuery({
    queryKey: ['api-profiles'],
    queryFn: endpoints.apiProfiles.list,
  });

  const templates = useMemo<Template[]>(
    () => templatesQuery.data ?? [],
    [templatesQuery.data],
  );
  const activeTemplate = templates.find((t) => t.code === templateCode);
  const selectedProfile = profilesQuery.data?.find((p) => p.id === selectedProfileId);

  useEffect(() => {
    const list = profilesQuery.data;
    if (list && list.length > 0 && selectedProfileId == null) {
      setSelectedProfileId(list[0].id);
      if (!selectedModel && list[0].default_model) {
        setSelectedModel(list[0].default_model);
      }
    }
  }, [profilesQuery.data, selectedProfileId, selectedModel, setSelectedProfileId, setSelectedModel]);

  useEffect(() => {
    setModels([]);
  }, [selectedProfileId]);

  useEffect(() => {
    if (templates.length > 0 && !templates.some((t) => t.code === templateCode)) {
      setTemplateCode(templates[0].code);
    }
  }, [templates, templateCode, setTemplateCode]);

  const isRunning = currentJob?.status === 'queued' || currentJob?.status === 'running';
  const selectedCount = selected.size;
  const totalCandidates = selectedCount * candidatesPerImage;
  const promptMissing =
    !!activeTemplate &&
    activeTemplate.placeholders.includes('prompt') &&
    prompt.trim() === '';
  const unknownPlaceholders = activeTemplate?.unknown_placeholders ?? [];

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

  const scanMutation = useMutation({
    mutationFn: ({ dir, recursive }: { dir: string; recursive: boolean }) =>
      endpoints.images.scan(dir, recursive),
    onSuccess: (resp) => {
      setItems(resp.items, resp.root);
      setLastScanDir(resp.root);
      setSourceType('scan');
      setScanModalOpen(false);
      selectAllValid();
      const validCount = resp.items.filter((i) => i.valid).length;
      message.success(`扫描完成：可用 ${validCount} 张`);
    },
    onError: (err: unknown) => {
      message.error(err instanceof ApiError ? err.detail : '扫描失败');
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => endpoints.images.upload(files),
    onSuccess: (resp) => {
      setItems(resp.items, resp.upload_dir);
      setSourceType('upload');
      selectAllValid();
      message.success(`已上传 ${resp.items.length} 张图片`);
    },
    onError: (err: unknown) => {
      message.error(err instanceof Error ? err.message : '上传失败');
    },
  });

  const fetchModelsMutation = useMutation({
    mutationFn: (id: number) => endpoints.apiProfiles.fetchModels(id),
    onSuccess: (resp) => {
      setModels(resp.models);
      if (resp.models.length === 0) {
        message.warning('外部接口返回 0 个模型');
      } else {
        message.success(`成功获取 ${resp.models.length} 个模型`);
        if (!selectedModel || !resp.models.some((m) => m.id === selectedModel)) {
          setSelectedModel(resp.models[0].id);
        }
      }
    },
    onError: (err: unknown) => {
      message.error(err instanceof ApiError ? err.detail : '获取模型失败');
    },
  });

  const submitMutation = useMutation({
    mutationFn: (payload: JobCreate) => endpoints.jobs.submit(payload),
    onSuccess: (job) => {
      setCurrentJob(job);
      message.success(`任务已提交：#${job.id}（${job.total_candidates} 候选）`);
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      void queryClient.invalidateQueries({ queryKey: ['job-detail'] });
    },
    onError: (err) => {
      notifyError(message, err);
    },
    onSettled: () => {
      submittingRef.current = false;
    },
  });

  const canStart =
    !isRunning &&
    !submitMutation.isPending &&
    !!selectedProfileId &&
    !!selectedModel &&
    selectedCount > 0 &&
    !promptMissing &&
    unknownPlaceholders.length === 0;

  const onStart = () => {
    if (isRunning || submitMutation.isPending || submittingRef.current) return;
    if (selectedCount === 0) return message.warning('请先选择要处理的图片');
    if (!selectedProfileId) return message.warning('请先选择 API 配置');
    if (!selectedModel) return message.warning('请先选择模型');
    if (promptMissing) return message.warning('当前模板需要填写提示词');
    if (unknownPlaceholders.length > 0) {
      return message.warning(
        `模板包含未支持的占位符：${unknownPlaceholders.map((u) => `{${u}}`).join(', ')}`,
      );
    }
    if (!canStart || !selectedProfileId || !selectedModel) return;

    submittingRef.current = true;
    submitMutation.mutate({
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
    });
  };

  const imageContent = (
    <div className="workflow-popover workflow-popover--source" onClick={stopPopoverClick}>
      <div className="workflow-popover__title">图片来源</div>
      <div className="workflow-upload-grid">
        <Button
          type={sourceType === 'scan' ? 'primary' : 'default'}
          icon={<FolderOpenOutlined />}
          loading={scanMutation.isPending}
          onClick={() => {
            setScanPath(lastScanDir);
            setScanModalOpen(true);
          }}
        >
          扫描本地目录
        </Button>
        <Button
          type={sourceType === 'upload' ? 'primary' : 'default'}
          icon={<UploadOutlined />}
          loading={uploadMutation.isPending}
          onClick={() => fileInputRef.current?.click()}
        >
          手动选择多张图片
        </Button>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*"
        style={{ display: 'none' }}
        onChange={(e) => {
          const fl = e.target.files;
          if (!fl || fl.length === 0) return;
          uploadMutation.mutate(Array.from(fl));
          e.target.value = '';
        }}
      />
      <Text type="secondary" className="workflow-popover__desc">
        当前已选择 {selectedCount} / {items.length} 张图片。
      </Text>
      {items.length > 0 && (
        <Button size="small" onClick={selectAllValid}>
          全选可用图片
        </Button>
      )}
    </div>
  );

  const modelOptions =
    models.length > 0
      ? models.map((m) => ({ value: m.id, label: m.id }))
      : selectedProfile?.default_model
        ? [{ value: selectedProfile.default_model, label: selectedProfile.default_model }]
        : [];
  const templateOptions = templates.map((t) => ({
    value: t.code,
    label: t.name,
  }));

  const advancedContent = (
    <div className="workflow-popover workflow-popover--model" onClick={stopPopoverClick}>
      <div className="workflow-popover__title">高级设置</div>
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <div>
          <Text type="secondary" className="workflow-field-label">API 配置</Text>
          <Select
            value={selectedProfileId ?? undefined}
            onChange={(v) => setSelectedProfileId(v)}
            placeholder="选择 API 配置"
            options={(profilesQuery.data ?? []).map((p) => ({
              value: p.id,
              label: `${p.name} (${p.base_url})`,
            }))}
            style={{ width: '100%' }}
          />
        </div>
        <div className="workflow-settings-grid">
          <div>
            <Text type="secondary" className="workflow-field-label">每张生成</Text>
            <InputNumber
              min={1}
              max={6}
              value={candidatesPerImage}
              disabled={!!isRunning}
              onChange={(v) => setCandidatesPerImage(v ?? 1)}
              style={{ width: '100%' }}
            />
          </div>
          <div>
            <Text type="secondary" className="workflow-field-label">重试次数</Text>
            <InputNumber
              min={1}
              max={5}
              value={retryMax}
              disabled={!autoRetry || !!isRunning}
              onChange={(v) => setRetryMax(v ?? 1)}
              style={{ width: '100%' }}
            />
          </div>
        </div>
        <div className="workflow-switch-row">
          <Text type="secondary">失败后自动重新生成</Text>
          <Switch checked={autoRetry} disabled={!!isRunning} onChange={setAutoRetry} />
        </div>
        <div>
          <Text type="secondary" className="workflow-field-label">输出目录</Text>
          <Input value={outputDir} disabled={!!isRunning} onChange={(e) => setOutputDir(e.target.value)} />
        </div>
      </Space>
    </div>
  );

  return (
    <>
      <section className="workflow-bar workflow-composer" aria-label="生成流程">
        <div className="workflow-composer__main">
          <Popover trigger="click" placement="bottomLeft" content={imageContent}>
            <button
              type="button"
              className={`workflow-reference-button ${selectedCount > 0 ? 'workflow-reference-button--active' : ''}`}
              aria-label={selectedCount > 0 ? `已选择 ${selectedCount} 张参考图` : '选择参考图片'}
              title={selectedCount > 0 ? `已选 ${selectedCount} 张` : '选择参考图'}
            >
              <PictureOutlined />
              {selectedCount > 0 && <em>{selectedCount}</em>}
            </button>
          </Popover>

          <Input.TextArea
            className={`workflow-prompt-input ${promptMissing ? 'workflow-prompt-input--warning' : ''}`}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={compactPrompt('')}
            maxLength={PROMPT_MAX}
            autoSize={{ minRows: 2, maxRows: 4 }}
            variant="borderless"
          />
        </div>

        <div className="workflow-composer__footer">
          <div className="workflow-composer__chips">
            <div className="workflow-inline-control workflow-inline-control--model">
              <ApiOutlined />
              <Select
                value={selectedModel ?? undefined}
                onChange={(v) => setSelectedModel(v)}
                placeholder="模型选择"
                options={modelOptions}
                variant="borderless"
                popupMatchSelectWidth={false}
                className="workflow-dark-select"
                popupClassName="workflow-dark-dropdown"
                suffixIcon={null}
              />
              <Tooltip title="获取模型">
                <Button
                  className="workflow-inline-refresh"
                  type="text"
                  size="small"
                  icon={<ReloadOutlined />}
                  loading={fetchModelsMutation.isPending}
                  disabled={!selectedProfileId}
                  onClick={() => {
                    if (selectedProfileId) fetchModelsMutation.mutate(selectedProfileId);
                  }}
                />
              </Tooltip>
            </div>
            <div className="workflow-inline-control workflow-inline-control--size">
              <SlidersOutlined />
              <Select
                value={selectedSize}
                onChange={setSelectedSize}
                options={SIZE_OPTIONS.map((s) => ({ value: s, label: s }))}
                variant="borderless"
                popupMatchSelectWidth={false}
                className="workflow-dark-select"
                popupClassName="workflow-dark-dropdown"
                suffixIcon={null}
              />
              <span className="workflow-inline-divider">·</span>
              <InputNumber
                min={1}
                max={6}
                value={candidatesPerImage}
                disabled={!!isRunning}
                onChange={(v) => setCandidatesPerImage(v ?? 1)}
                variant="borderless"
                controls={false}
                className="workflow-dark-number"
              />
              <span className="workflow-inline-suffix">张</span>
            </div>
            <div className="workflow-inline-control workflow-inline-control--template">
              <Select
                value={templateCode}
                onChange={setTemplateCode}
                options={templateOptions}
                variant="borderless"
                popupMatchSelectWidth={false}
                className="workflow-dark-select"
                popupClassName="workflow-dark-dropdown"
                suffixIcon={null}
              />
            </div>
            <Popover trigger="click" placement="topLeft" content={advancedContent}>
              <button type="button" className="workflow-chip workflow-chip--settings">
                <SlidersOutlined />
                <span>高级设置</span>
              </button>
            </Popover>
          </div>

          <div className="workflow-composer__actions">
            <span className="workflow-counter">{prompt.length}/{PROMPT_MAX}</span>
            <Button
              className="workflow-start-button"
              type="primary"
              size="large"
              icon={<PlayCircleOutlined />}
              loading={submitMutation.isPending}
              disabled={!canStart}
              onClick={onStart}
            >
              {totalCandidates > 0 ? totalCandidates : ''}
            </Button>
          </div>
        </div>
      </section>

      <Modal
        title="选择本地图片文件夹"
        open={scanModalOpen}
        onOk={() => {
          if (!scanPath.trim()) {
            message.warning('请输入目录路径');
            return;
          }
          scanMutation.mutate({ dir: scanPath.trim(), recursive: scanRecursive });
        }}
        confirmLoading={scanMutation.isPending}
        onCancel={() => setScanModalOpen(false)}
        okText="扫描"
        cancelText="取消"
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Input
            value={scanPath}
            onChange={(e) => setScanPath(e.target.value)}
            placeholder="例如：/app/data/uploads 或 D:/images（容器内可见路径）"
            autoFocus
          />
          <Checkbox checked={scanRecursive} onChange={(e) => setScanRecursive(e.target.checked)}>
            递归扫描子目录
          </Checkbox>
          <Text type="secondary" style={{ fontSize: 12 }}>
            如需扫描宿主机目录，请先在 docker-compose.yml 中添加 volume 挂载。
          </Text>
        </Space>
      </Modal>
    </>
  );
}
