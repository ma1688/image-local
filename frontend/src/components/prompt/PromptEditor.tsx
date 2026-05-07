import { Card, Input, Space, Tag, Typography } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { useWorkbenchStore } from '@/store/workbenchStore';

const { Text } = Typography;
const PROMPT_MAX = 1000;

export default function PromptEditor() {
  const { prompt, setPrompt } = useWorkbenchStore();

  return (
    <Card
      size="small"
      className="workbench-card"
      title={
        <Space>
          <EditOutlined />
          <span>提示词</span>
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
      <Text type="secondary" style={{ fontSize: 12, marginTop: 6, display: 'block' }}>
        提示：选择"自定义流程"模板时本输入框为空白；选择内置模板时，模板内的占位符
        <code> {'{prompt}'} </code>
        会被替换为此处内容。
      </Text>
    </Card>
  );
}
