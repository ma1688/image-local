import { useMemo, useRef, useState } from 'react';
import {
  App,
  Button,
  Card,
  Checkbox,
  Empty,
  Input,
  Modal,
  Segmented,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  ClearOutlined,
  FileImageOutlined,
  FolderOpenOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { useMutation } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { endpoints } from '@/api/endpoints';
import type { ImageItem } from '@/api/types';
import { useImageSourceStore } from '@/store/imageSourceStore';

const { Text } = Typography;

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function ImageSource() {
  const { message } = App.useApp();
  const {
    sourceType,
    lastScanDir,
    items,
    selected,
    rootLabel,
    setSourceType,
    setLastScanDir,
    setItems,
    toggleSelected,
    selectAllValid,
    clearAll,
  } = useImageSourceStore();

  const [scanModalOpen, setScanModalOpen] = useState(false);
  const [scanPath, setScanPath] = useState(lastScanDir);
  const [scanRecursive, setScanRecursive] = useState(false);

  const scanMutation = useMutation({
    mutationFn: ({ dir, recursive }: { dir: string; recursive: boolean }) =>
      endpoints.images.scan(dir, recursive),
    onSuccess: (resp) => {
      setItems(resp.items, resp.root);
      setLastScanDir(resp.root);
      setSourceType('scan');
      setScanModalOpen(false);
      const validCount = resp.items.filter((i) => i.valid).length;
      message.success(
        `扫描完成：共 ${resp.total_seen} 张${resp.truncated ? '（已截断为前 1000 张）' : ''}，可用 ${validCount} 张`,
      );
    },
    onError: (err: unknown) => {
      message.error(err instanceof ApiError ? err.detail : '扫描失败');
    },
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => endpoints.images.upload(files),
    onSuccess: (resp) => {
      setItems(resp.items, resp.upload_dir);
      setSourceType('upload');
      message.success(`已上传 ${resp.items.length} 张图片到 ${resp.upload_dir}`);
    },
    onError: (err: unknown) => {
      message.error(err instanceof Error ? err.message : '上传失败');
    },
  });

  const totalSizeBytes = useMemo(
    () => items.reduce((acc, it) => acc + it.size_bytes, 0),
    [items],
  );

  return (
    <Card
      size="small"
      className="workbench-card"
      title={
        <Space>
          <FileImageOutlined />
          <span>图片来源</span>
          {rootLabel && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              · {rootLabel}
            </Text>
          )}
        </Space>
      }
      extra={
        items.length > 0 && (
          <Space>
            <Tooltip title="全选可用图片">
              <Button size="small" onClick={selectAllValid}>
                全选
              </Button>
            </Tooltip>
            <Tooltip title="清空当前列表">
              <Button size="small" icon={<ClearOutlined />} onClick={clearAll}>
                清空
              </Button>
            </Tooltip>
          </Space>
        )
      }
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Segmented
          block
          value={sourceType}
          onChange={(v) => setSourceType(v as 'scan' | 'upload')}
          options={[
            {
              label: (
                <Space size={4}>
                  <FolderOpenOutlined />
                  扫描本地目录
                </Space>
              ),
              value: 'scan',
            },
            {
              label: (
                <Space size={4}>
                  <UploadOutlined />
                  手动选择多张图片
                </Space>
              ),
              value: 'upload',
            },
          ]}
        />

        {sourceType === 'scan' ? (
          <Button
            type="primary"
            icon={<FolderOpenOutlined />}
            block
            loading={scanMutation.isPending}
            onClick={() => {
              setScanPath(lastScanDir);
              setScanModalOpen(true);
            }}
          >
            选择图片文件夹
          </Button>
        ) : (
          <>
            <Button
              type="primary"
              icon={<UploadOutlined />}
              block
              loading={uploadMutation.isPending}
              onClick={() => fileInputRef.current?.click()}
            >
              手动选择多张图片
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                const fl = e.target.files;
                if (!fl || fl.length === 0) return;
                uploadMutation.mutate(Array.from(fl));
                e.target.value = '';
              }}
            />
          </>
        )}

        {scanMutation.isPending && <Spin tip="扫描中…" />}

        {!scanMutation.isPending && items.length === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="未选择任何图片"
            style={{ padding: '12px 0' }}
          />
        )}

        {items.length > 0 && (
          <>
            <div className="image-list">
              {items.map((it) => (
                <ImageRow
                  key={it.path}
                  item={it}
                  checked={selected.has(it.path)}
                  onToggle={() => toggleSelected(it.path)}
                />
              ))}
            </div>
            <Space>
              <Text type="secondary">
                已选择 {selected.size} 张，共 {items.length} 张
              </Text>
              <Tag color="blue">{formatSize(totalSizeBytes)}</Tag>
            </Space>
          </>
        )}
      </Space>

      <Modal
        title="选择本地图片文件夹"
        open={scanModalOpen}
        onOk={() => {
          if (!scanPath.trim()) {
            message.warning('请输入目录路径');
            return;
          }
          scanMutation.mutate({ dir: scanPath.trim(), recursive: scanRecursive });
        }}
        confirmLoading={scanMutation.isPending}
        onCancel={() => setScanModalOpen(false)}
        okText="扫描"
        cancelText="取消"
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Input
            value={scanPath}
            onChange={(e) => setScanPath(e.target.value)}
            placeholder="例如：/app/data/uploads 或 D:/images（容器内可见路径）"
            autoFocus
          />
          <Checkbox checked={scanRecursive} onChange={(e) => setScanRecursive(e.target.checked)}>
            递归扫描子目录
          </Checkbox>
          <Text type="secondary" style={{ fontSize: 12 }}>
            提示：当前栈运行在 Docker 容器中，扫描的是容器内可见的路径。如需扫描宿主机目录，请在
            docker-compose.yml 中加 volume 挂载。
          </Text>
        </Space>
      </Modal>
    </Card>
  );
}

interface ImageRowProps {
  item: ImageItem;
  checked: boolean;
  onToggle: () => void;
}

function ImageRow({ item, checked, onToggle }: ImageRowProps) {
  return (
    <div
      className="image-row"
    >
      <Checkbox checked={checked} disabled={!item.valid} onChange={onToggle} />
      <div
        className="image-row__thumb"
      >
        {item.valid && item.thumb_url ? (
          <img
            src={item.thumb_url}
            alt={item.name}
            loading="lazy"
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <FileImageOutlined style={{ color: '#bfbfbf' }} />
        )}
      </div>
      <div className="image-row__meta">
        <div
          className="image-row__name"
          title={item.path}
        >
          {item.name}
        </div>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {formatSize(item.size_bytes)}
          {item.width && item.height ? ` · ${item.width}×${item.height}` : ''}
          {item.reason ? ` · ${item.reason}` : ''}
        </Text>
      </div>
    </div>
  );
}
