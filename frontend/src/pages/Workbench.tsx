import { useEffect, useState } from 'react';
import { Badge, Layout, Space, Tag, Typography } from 'antd';
import { PictureOutlined } from '@ant-design/icons';
import { endpoints } from '@/api/endpoints';
import type { HealthResponse } from '@/api/types';
import HistoryPanel from '@/components/history/HistoryPanel';
import ResultsList from '@/components/results/ResultsList';
import StatsHeader from '@/components/workbench/StatsHeader';
import StorageBanner from '@/components/workbench/StorageBanner';
import Toolbar from '@/components/workbench/Toolbar';
import WorkflowBar from '@/components/workbench/WorkflowBar';

const { Content } = Layout;
const { Title, Text } = Typography;

function HealthBadge() {
  const [h, setH] = useState<HealthResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    endpoints
      .health()
      .then(setH)
      .catch((e: Error) => setErr(e.message));
  }, []);

  if (err) return <Tag color="error">后端不可达</Tag>;
  if (!h) return <Tag>检查中…</Tag>;

  return (
    <Space size={8} wrap>
      <Badge status={h.db_ok ? 'success' : 'warning'} text="db" />
      <Badge status={h.redis_ok ? 'success' : 'warning'} text="redis" />
      <Tag color="blue" style={{ marginInlineEnd: 0 }}>
        {h.task_backend}
      </Tag>
    </Space>
  );
}

export default function Workbench() {
  return (
    <Layout className="workbench-shell">
      <Content className="workbench-content">
        <section className="workbench-topbar" aria-label="工作台概览">
          <div className="workbench-brand">
            <div className="workbench-brand__icon">
              <PictureOutlined />
            </div>
            <div className="workbench-brand__copy">
              <Title level={3} className="workbench-title">
                本地批量图片生成工作台
              </Title>
              <Text className="workbench-subtitle">
                本地化批量图片生成工具，支持多流程模板与本地接口调用
              </Text>
            </div>
          </div>
          <div className="workbench-health" aria-label="后端健康状态">
            <HealthBadge />
          </div>
          <StatsHeader />
        </section>

        <Toolbar />
        <StorageBanner />
        <WorkflowBar />

        <div className="workbench-results-grid">
          <ResultsList />
          <HistoryPanel />
        </div>
      </Content>
    </Layout>
  );
}
