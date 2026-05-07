import { Empty, Typography } from 'antd';
import type { ReactNode } from 'react';

const { Text } = Typography;

interface EmptyHintProps {
  title?: string;
  description?: ReactNode;
  /** 紧凑模式：用于面板内嵌（更小的留白） */
  compact?: boolean;
  /** 用于操作引导（例如"上传图片"按钮） */
  action?: ReactNode;
}

/**
 * 工作台统一的空态：
 * - 视觉一致（Empty.PRESENTED_IMAGE_SIMPLE）
 * - 描述文字默认为 secondary text，避免抢镜
 * - 可选 action：例如 history 空态可放"创建任务"快捷入口
 */
export default function EmptyHint({
  title,
  description,
  compact,
  action,
}: EmptyHintProps) {
  return (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={
        description ?? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {title ?? '暂无数据'}
          </Text>
        )
      }
      style={{ padding: compact ? '12px 0' : '24px 0' }}
    >
      {action}
    </Empty>
  );
}
