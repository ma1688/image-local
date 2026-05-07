import { Card, Empty, Tag, Typography } from 'antd';

const { Text } = Typography;

interface Props {
  title: string;
  milestone: string;
  description: string;
  height?: number;
}

export default function PlaceholderCard({ title, milestone, description, height = 220 }: Props) {
  return (
    <Card
      size="small"
      className="workbench-card"
      title={title}
      extra={<Tag color="processing">待 {milestone}</Tag>}
    >
      <div className="placeholder-card__empty" style={{ minHeight: height }}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <Text type="secondary" style={{ fontSize: 12 }}>
              {description}
            </Text>
          }
        />
      </div>
    </Card>
  );
}
