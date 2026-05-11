import { useMemo } from 'react';
import {
  App,
  Button,
  Input,
  InputNumber,
  Popover,
  Radio,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  AppstoreOutlined,
  FileImageOutlined,
  PlayCircleOutlined,
  RightOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';
import { notifyError } from '@/api/messages';
import type { JobCreate, Template } from '@/api/types';
import ApiConfigForm from '@/components/api-config/ApiConfigForm';
import { useConfigStore } from '@/store/configStore';
import { useImageSourceStore } from '@/store/imageSourceStore';
import { useJobStore } from '@/store/jobStore';
import { useWorkbenchStore } from '@/store/workbenchStore';

const { Text } = Typography;
const PROMPT_MAX = 1000;

interface WorkflowBarProps {
  onPickImages?: () => void;
}

function stopPopoverClick(e: React.MouseEvent) {
  e.stopPropagation();
}

export default function WorkflowBar({ onPickImages }: WorkflowBarProps) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const items = useImageSourceStore((s) => s.items);
  const selected = useImageSourceStore((s) => s.selected);
  const { templateCode, setTemplateCode, prompt, setPrompt } = useWorkbenchStore();
  const {
    selectedProfileId,
    selectedModel,
    selectedSize,
    candidatesPerImage,
    autoRetry,
    retryMax,
    outputDir,
    setCandidatesPerImage,
  } = useConfigStore();
  const { currentJob, setCurrentJob } = useJobStore();

  const templatesQuery = useQuery({
    queryKey: ['templates'],
    queryFn: endpoints.templates.list,
  });

  const templates = useMemo<Template[]>(
    () => templatesQuery.data ?? [],
    [templatesQuery.data],
  );
  const activeTemplate = templates.find((t) => t.code === templateCode);
  const promptMissing =
    !!activeTemplate &&
    activeTemplate.placeholders.includes('prompt') &&
    prompt.trim() === '';
  const unknownPlaceholders = activeTemplate?.unknown_placeholders ?? [];
  const selectedCount = selected.size;
  const totalCandidates = selectedCount * candidatesPerImage;
  const isRunning = currentJob?.status === 'queued' || currentJob?.status === 'running';

  const submitMutation = useMutation({
    mutationFn: (payload: JobCreate) => endpoints.jobs.submit(payload),
    onSuccess: (job) => {
      setCurrentJob(job);
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      void queryClient.invalidateQueries({ queryKey: ['job-detail'] });
    },
    onError: (err) => {
      notifyError(message, err);
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
    if (selectedCount === 0) {
      message.warning('请先选择要处理的图片');
      return;
    }
    if (!selectedProfileId) {
      message.warning('请先选择 API 配置');
      return;
    }
    if (!selectedModel) {
      message.warning('请先选择模型');
      return;
    }
    if (promptMissing) {
      message.warning('当前模板需要填写提示词');
      return;
    }
    if (unknownPlaceholders.length > 0) {
      message.warning(`模板包含未支持的占位符：${unknownPlaceholders.map((u) => `{${u}}`).join(', ')}`);
      return;
    }
    if (!canStart || !selectedModel || !selectedProfileId) return;
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

  const imageContent = (
    <div className="workflow-popover workflow-popover--source" onClick={stopPopoverClick}>
      <div className="workflow-popover__title">图片来源</div>
      <Text type="secondary" className="workflow-popover__desc">
        当前已选择 {selectedCount} / {items.length} 张图片。
      </Text>
      <Button
        type="primary"
        icon={<UploadOutlined />}
        block
        onClick={onPickImages}
        style={{ marginTop: 12 }}
      >
        打开图片来源面板
      </Button>
    </div>
  );

  const templateContent = (
    <div className="workflow-popover workflow-popover--template" onClick={stopPopoverClick}>
      <div className="workflow-popover__title">流程模板</div>
      <Radio.Group
        value={templateCode}
        onChange={(e) => setTemplateCode(e.target.value)}
        className="workflow-template-list"
      >
        {templates.map((t) => (
          <Radio.Button key={t.code} value={t.code} className="workflow-template-option">
            <div className="workflow-template-option__name">
              {t.name}
              {t.builtin && <Tag color="gold">内置</Tag>}
            </div>
            <div className="workflow-template-option__meta">
              {t.default_size ?? '自定义尺寸'}
              {t.default_model ? ` · ${t.default_model}` : ''}
            </div>
          </Radio.Button>
        ))}
      </Radio.Group>
    </div>
  );

  const promptContent = (
    <div className="workflow-popover workflow-popover--prompt" onClick={stopPopoverClick}>
      <div className="workflow-popover__title-row">
        <div className="workflow-popover__title">提示词</div>
        <Tag color={prompt.length > PROMPT_MAX ? 'red' : 'default'}>
          {prompt.length} / {PROMPT_MAX}
        </Tag>
      </div>
      <Input.TextArea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="输入这次生成要强调的风格、画面、材质或限制……"
        maxLength={PROMPT_MAX}
        autoSize={{ minRows: 5, maxRows: 8 }}
        autoFocus
      />
      <Text type="secondary" className="workflow-popover__desc">
        当前模板中的 <code>{'{prompt}'}</code> 会替换为这里的内容。
      </Text>
    </div>
  );

  return (
    <section className="workflow-bar" aria-label="生成流程">
      <Popover trigger="click" placement="bottomLeft" content={imageContent}>
        <button type="button" className="workflow-step workflow-step--source">
          <div className="workflow-step__inner">
            <FileImageOutlined className="workflow-step__icon workflow-step__icon--blue" />
            <div className="workflow-step__content">
              <div className="workflow-step__label-row">
                <span>图片来源</span>
                {selectedCount > 0 && <Tag color="blue">{selectedCount} 张</Tag>}
              </div>
              <div className="workflow-step__title">
                {selectedCount > 0 ? `已选择 ${selectedCount} 张` : '选择图片'}
              </div>
              <div className="workflow-step__meta">
                {items.length > 0 ? `共 ${items.length} 张候选图片` : '扫描目录或手动上传'}
              </div>
            </div>
          </div>
        </button>
      </Popover>

      <RightOutlined className="workflow-arrow" />

      <Popover trigger="click" placement="bottomLeft" content={templateContent}>
        <button type="button" className="workflow-step workflow-step--template">
          <div className="workflow-step__inner">
            <AppstoreOutlined className="workflow-step__icon workflow-step__icon--amber" />
            <div className="workflow-step__content">
              <div className="workflow-step__label-row">
                <span>流程模板</span>
                {activeTemplate?.builtin && <Tag color="gold">内置</Tag>}
              </div>
              <div className="workflow-step__title">
                {activeTemplate?.name ?? '选择流程'}
              </div>
              <div className="workflow-step__meta">
                {activeTemplate?.default_size ?? selectedSize}
                {activeTemplate?.default_model ? ` · ${activeTemplate.default_model}` : ''}
              </div>
            </div>
          </div>
        </button>
      </Popover>

      <RightOutlined className="workflow-arrow" />

      <Popover trigger="click" placement="bottom" content={promptContent}>
        <button type="button" className="workflow-step workflow-step--prompt">
          <div className="workflow-step__inner workflow-step__inner--prompt">
            <div className="workflow-step__content workflow-step__content--center">
              <div className="workflow-step__label-row workflow-step__label-row--center">
                提示词
              </div>
              <Tooltip title={prompt || '点击填写提示词'}>
                <div className="workflow-step__prompt-preview">
                  {prompt || '点击填写提示词'}
                </div>
              </Tooltip>
            </div>
          </div>
        </button>
      </Popover>

      <RightOutlined className="workflow-arrow" />

      <ApiConfigForm variant="workflow" />

      <div className="workflow-start">
        <Space.Compact>
          <InputNumber
            className="workflow-start__count"
            min={1}
            max={6}
            value={candidatesPerImage}
            disabled={!!isRunning}
            onChange={(v) => setCandidatesPerImage(v ?? 1)}
            addonBefore="×"
          />
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            loading={submitMutation.isPending}
            disabled={!canStart}
            onClick={onStart}
          >
            开始生成
          </Button>
        </Space.Compact>
        <div className="workflow-start__meta">
          {selectedCount > 0 ? `${selectedCount} 张 × ${candidatesPerImage} = ${totalCandidates} 候选` : '先选择图片'}
        </div>
      </div>
    </section>
  );
}
