import { useMemo } from 'react';
import { Alert, Card, Input, Space, Tag, Typography } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';
import { useWorkbenchStore } from '@/store/workbenchStore';

const { Text } = Typography;
const PROMPT_MAX = 1000;

export default function PromptEditor() {
  const { prompt, setPrompt, templateCode } = useWorkbenchStore();

  const templatesQuery = useQuery({
    queryKey: ['templates'],
    queryFn: endpoints.templates.list,
    staleTime: 30_000,
  });

  const tpl = useMemo(
    () => (templatesQuery.data ?? []).find((t) => t.code === templateCode),
    [templatesQuery.data, templateCode],
  );

  // 校验逻辑与后端 services/prompt_template.py 对齐：
  // - 模板含 {prompt} 但当前输入为空 -> warning
  // - 模板含未知占位符 -> warning（创建任务时后端会 400 阻断）
  const warnPromptRequired =
    !!tpl && tpl.placeholders.includes('prompt') && prompt.trim() === '';
  const unknown = tpl?.unknown_placeholders ?? [];
  const showAlert = warnPromptRequired || unknown.length > 0;

  return (
    <Card
      size="small"
      className="workbench-card"
      title={
        <Space>
          <EditOutlined />
          <span>提示词</span>
          {tpl && tpl.placeholders.length > 0 && (
            <Tag color="geekblue" style={{ marginInlineEnd: 0 }}>
              占位符: {tpl.placeholders.map((p) => `{${p}}`).join(' ')}
            </Tag>
          )}
        </Space>
      }
      extra={
        <Tag color={prompt.length > PROMPT_MAX ? 'red' : 'default'}>
          {prompt.length} / {PROMPT_MAX}
        </Tag>
      }
    >
      <Input.TextArea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="例如：将参考图改造成圣诞节主题贺卡，保留主体结构，背景换成圣诞树和雪花……"
        autoSize={{ minRows: 5, maxRows: 7 }}
        maxLength={PROMPT_MAX}
        showCount={false}
      />
      {showAlert && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 8 }}
          message={
            warnPromptRequired
              ? '当前模板包含 {prompt} 占位符，请填写本输入框作为提示词主体'
              : `模板包含未支持的占位符：${unknown.map((u) => `{${u}}`).join(', ')}`
          }
          description={
            unknown.length > 0
              ? '后端目前仅支持 {prompt}，请先去模板设置中删除未知占位符再提交任务'
              : null
          }
        />
      )}
      <Text type="secondary" style={{ fontSize: 12, marginTop: 6, display: 'block' }}>
        提示：选择"自定义流程"模板时本输入框为空白；选择内置模板时，模板内的占位符
        <code> {'{prompt}'} </code>
        会被替换为此处内容。
      </Text>
    </Card>
  );
}
