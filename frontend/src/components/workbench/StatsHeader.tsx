import { Card, Progress, Typography } from 'antd';
import {
  AppstoreAddOutlined,
  CheckCircleOutlined,
  HomeFilled,
} from '@ant-design/icons';
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

  const pending = items.filter((i) => i.valid).length;
  const selectedCount = selected.size;
  const generated = currentJob ? currentJob.succeeded_count : 0;
  const totalCandidates = currentJob ? currentJob.total_candidates : 0;
  const finished = currentJob
    ? currentJob.succeeded_count + currentJob.failed_count
    : 0;
  const overallPct = totalCandidates > 0 ? Math.round((finished / totalCandidates) * 100) : 0;

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
    </div>
  );
}
