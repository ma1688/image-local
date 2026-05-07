import { useEffect, useMemo } from 'react';
import { Card, Empty, Space, Spin, Tabs, Tag, Typography } from 'antd';
import { AppstoreOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';
import type { Template } from '@/api/types';
import { useWorkbenchStore } from '@/store/workbenchStore';

const { Text, Paragraph } = Typography;

export default function TemplateTabs() {
  const { templateCode, setTemplateCode } = useWorkbenchStore();
  const templatesQuery = useQuery({
    queryKey: ['templates'],
    queryFn: endpoints.templates.list,
  });

  const list = useMemo<Template[]>(() => templatesQuery.data ?? [], [templatesQuery.data]);

  useEffect(() => {
    if (list.length > 0 && !list.some((t) => t.code === templateCode)) {
      setTemplateCode(list[0].code);
    }
  }, [list, templateCode, setTemplateCode]);

  const active = list.find((t) => t.code === templateCode);

  return (
    <Card
      size="small"
      className="workbench-card"
      title={
        <Space>
          <AppstoreOutlined />
          <span>流程模板</span>
        </Space>
      }
    >
      {templatesQuery.isLoading && <Spin tip="加载模板…" />}
      {!templatesQuery.isLoading && list.length === 0 && (
        <Empty description="未找到流程模板" />
      )}
      {list.length > 0 && (
        <>
          <Tabs
            activeKey={templateCode}
            onChange={setTemplateCode}
            size="small"
            items={list.map((t) => ({
              key: t.code,
              label: (
                <Space size={4}>
                  {t.name}
                  {t.builtin && (
                    <Tag color="gold" style={{ marginInlineEnd: 0 }}>
                      内置
                    </Tag>
                  )}
                </Space>
              ),
            }))}
          />
          {active && (
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                code: <code>{active.code}</code>
                {active.default_size && (
                  <>
                    {' · '}默认尺寸: <code>{active.default_size}</code>
                  </>
                )}
                {active.default_model && (
                  <>
                    {' · '}默认模型: <code>{active.default_model}</code>
                  </>
                )}
              </Text>
              <Paragraph
                className="template-preview"
                style={{
                  marginBottom: 0,
                  fontSize: 12,
                  padding: '8px 10px',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {active.prompt_template || <em>（自定义流程不预设模板，直接使用上方提示词）</em>}
              </Paragraph>
            </Space>
          )}
        </>
      )}
    </Card>
  );
}
