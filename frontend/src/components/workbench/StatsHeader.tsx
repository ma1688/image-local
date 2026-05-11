import { Card, Popover, Progress, Typography } from 'antd';
import {
  AppstoreAddOutlined,
  CheckCircleOutlined,
  FileTextOutlined,
  SettingOutlined,
  HomeFilled,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';
import ApiConfigForm from '@/components/api-config/ApiConfigForm';
import LogStream from '@/components/log/LogStream';
import { useConfigStore } from '@/store/configStore';
import { useImageSourceStore } from '@/store/imageSourceStore';
import { useJobStore } from '@/store/jobStore';

const { Text } = Typography;

interface StatItemProps {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  tone: 'blue' | 'green' | 'amber';
}

function StatItem({ icon, label, value, tone }: StatItemProps) {
  return (
    <Card size="small" className={`workbench-card stats-card stats-card--${tone}`}>
      <div className="stats-card__body">
        <div className="stats-card__icon">{icon}</div>
        <div className="stats-card__content">
          <Text className="stats-card__label">{label}</Text>
          <div className="stats-card__value">{value}</div>
        </div>
      </div>
    </Card>
  );
}

export default function StatsHeader() {
  const items = useImageSourceStore((s) => s.items);
  const selected = useImageSourceStore((s) => s.selected);
  const currentJob = useJobStore((s) => s.currentJob);
  const events = useJobStore((s) => s.events);
  const selectedProfileId = useConfigStore((s) => s.selectedProfileId);
  const selectedModel = useConfigStore((s) => s.selectedModel);
  const selectedSize = useConfigStore((s) => s.selectedSize);
  const profilesQuery = useQuery({
    queryKey: ['api-profiles'],
    queryFn: endpoints.apiProfiles.list,
  });

  const pending = items.filter((i) => i.valid).length;
  const selectedCount = selected.size;
  const generated = currentJob ? currentJob.succeeded_count : 0;
  const totalCandidates = currentJob ? currentJob.total_candidates : 0;
  const finished = currentJob
    ? currentJob.succeeded_count + currentJob.failed_count
    : 0;
  const overallPct = totalCandidates > 0 ? Math.round((finished / totalCandidates) * 100) : 0;
  const selectedProfile = profilesQuery.data?.find((p) => p.id === selectedProfileId);

  return (
    <div className="stats-header">
      <StatItem
        icon={<HomeFilled />}
        label="待处理图片数量"
        value={pending}
        tone="blue"
      />
      <StatItem
        icon={<AppstoreAddOutlined />}
        label="已生成数量 / 总数量"
        value={
          <span>
            {generated} <span className="stats-card__muted">/ {totalCandidates}</span>
          </span>
        }
        tone="green"
      />
      <StatItem
        icon={<CheckCircleOutlined />}
        label="已选中数量"
        value={selectedCount}
        tone="amber"
      />
      <Card size="small" className="workbench-card stats-progress-card">
        <div className="stats-progress-card__head">
          <Text className="stats-card__label">整体进度</Text>
          <Text strong className="stats-progress-card__percent">
            {overallPct}%
          </Text>
        </div>
        <Progress
          percent={overallPct}
          showInfo={false}
          size={[220, 9]}
          strokeColor="#16a34a"
          trailColor="#edf2f7"
          status={overallPct === 100 ? 'success' : 'normal'}
        />
      </Card>
      <Popover
        trigger="click"
        placement="bottomRight"
        arrow={false}
        destroyOnHidden
        overlayClassName="api-config-popover"
        content={<ApiConfigForm embedded />}
      >
        <Card
          size="small"
          className="workbench-card stats-card stats-card--config"
          role="button"
          tabIndex={0}
          aria-label="打开 API 配置"
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              e.currentTarget.click();
            }
          }}
        >
          <div className="stats-card__body">
            <div className="stats-card__icon">
              <SettingOutlined />
            </div>
            <div className="stats-card__content">
              <Text className="stats-card__label">API 配置</Text>
              <div className="stats-card__value stats-card__value--small">
                {selectedProfile?.name ?? '点击配置'}
              </div>
              <div className="stats-card__meta">
                {selectedModel ?? selectedProfile?.default_model ?? '未选模型'} · {selectedSize}
              </div>
            </div>
          </div>
        </Card>
      </Popover>
      <Popover
        trigger="click"
        placement="bottomRight"
        arrow={false}
        destroyOnHidden={false}
        overlayClassName="log-popover"
        content={<LogStream embedded />}
      >
        <Card
          size="small"
          className="workbench-card stats-card stats-card--log"
          role="button"
          tabIndex={0}
          aria-label="打开运行日志"
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              e.currentTarget.click();
            }
          }}
        >
          <div className="stats-card__body">
            <div className="stats-card__icon">
              <FileTextOutlined />
            </div>
            <div className="stats-card__content">
              <Text className="stats-card__label">运行日志</Text>
              <div className="stats-card__value stats-card__value--small">
                {events.length > 0 ? `${events.length} 条` : '下拉查看'}
              </div>
              <div className="stats-card__meta">
                {currentJob ? `Job #${currentJob.id} · ${currentJob.status}` : '尚未提交任务'}
              </div>
            </div>
          </div>
        </Card>
      </Popover>
    </div>
  );
}
