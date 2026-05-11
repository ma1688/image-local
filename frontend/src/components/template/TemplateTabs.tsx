import { useEffect, useMemo } from 'react';
import { Card, Empty, Radio, Space, Spin, Typography } from 'antd';
import { AppstoreOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';
import type { Template } from '@/api/types';
import { useWorkbenchStore } from '@/store/workbenchStore';

const { Paragraph } = Typography;

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
      className="workbench-card template-card"
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
          <Radio.Group
            className="template-picker"
            value={templateCode}
            onChange={(e) => setTemplateCode(e.target.value)}
          >
            {list.map((t) => (
              <Radio.Button key={t.code} value={t.code} className="template-picker__item">
                <span className="template-picker__name">{t.name}</span>
                {t.builtin && <span className="template-picker__badge">内置</span>}
              </Radio.Button>
            ))}
          </Radio.Group>
          {active && (
            <Space className="template-detail" direction="vertical" size={8}>
              <div className="template-meta-grid">
                <div className="template-meta-chip">
                  <span>code</span>
                  <code>{active.code}</code>
                </div>
                {active.default_size && (
                  <div className="template-meta-chip">
                    <span>默认尺寸</span>
                    <code>{active.default_size}</code>
                  </div>
                )}
                {active.default_model && (
                  <div className="template-meta-chip">
                    <span>默认模型</span>
                    <code>{active.default_model}</code>
                  </div>
                )}
              </div>
              <Paragraph
                className="template-preview"
                style={{
                  marginBottom: 0,
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
