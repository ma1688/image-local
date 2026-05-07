import { useQuery } from '@tanstack/react-query';
import { Tooltip } from 'antd';
import { WarningFilled } from '@ant-design/icons';
import { endpoints } from '@/api/endpoints';

function fmtBytes(n: number): string {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 10 ? 0 : 1)} ${units[i]}`;
}

/**
 * 存储警告横幅：仅在后端报告 status='warn' 或 'critical' 时显示，
 * 提示用户清理 outputs/uploads/thumbs。
 *
 * 数据每 30 秒拉一次，避免对 IO 造成压力（下盘走 rglob，目录大时较慢）。
 */
export default function StorageBanner() {
  const q = useQuery({
    queryKey: ['storage-usage'],
    queryFn: endpoints.storage.usage,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  });

  if (!q.data) return null;
  if (q.data.status === 'ok') return null;

  const className =
    q.data.status === 'critical'
      ? 'storage-warn-banner storage-warn-banner--critical'
      : 'storage-warn-banner storage-warn-banner--warn';

  const title =
    q.data.status === 'critical'
      ? '已超过存储硬上限：建议立即清理 outputs/uploads，否则可能阻断新任务'
      : '存储占用接近警戒值：建议在工作台外手动清理 outputs/uploads';

  const detail =
    `已用 ${fmtBytes(q.data.total_bytes)} / 警戒 ${fmtBytes(q.data.warn_bytes)}` +
    (q.data.hard_limit_bytes > 0
      ? ` · 上限 ${fmtBytes(q.data.hard_limit_bytes)}`
      : '') +
    ` · 磁盘空闲 ${fmtBytes(q.data.disk_free_bytes)}`;

  return (
    <Tooltip title={detail}>
      <div className={className} role="status" aria-live="polite">
        <WarningFilled />
        <span>{title}</span>
        <span style={{ marginLeft: 'auto', opacity: 0.8 }}>{detail}</span>
      </div>
    </Tooltip>
  );
}
