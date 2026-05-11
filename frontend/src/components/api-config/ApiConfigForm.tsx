import { useEffect, useMemo, useState } from 'react';
import {
  App,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Tag,
  Tooltip,
} from 'antd';
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { endpoints } from '@/api/endpoints';
import type {
  ApiProfile,
  ApiProfileCreate,
  ApiProfileUpdate,
  ModelInfo,
} from '@/api/types';
import { useConfigStore } from '@/store/configStore';

const SIZE_OPTIONS = ['512x512', '768x768', '1024x1024', '1024x1536', '1536x1024', '2048x2048'];

interface ApiConfigFormProps {
  embedded?: boolean;
}

interface ProfileFormValues {
  name: string;
  base_url: string;
  api_key: string;
  default_model?: string;
}

export default function ApiConfigForm({ embedded = false }: ApiConfigFormProps) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [createForm] = Form.useForm<ProfileFormValues>();
  const [editForm] = Form.useForm<ProfileFormValues>();

  const { selectedProfileId, selectedModel, selectedSize } = useConfigStore();
  const setSelectedProfileId = useConfigStore((s) => s.setSelectedProfileId);
  const setSelectedModel = useConfigStore((s) => s.setSelectedModel);
  const setSelectedSize = useConfigStore((s) => s.setSelectedSize);

  const profilesQuery = useQuery({
    queryKey: ['api-profiles'],
    queryFn: endpoints.apiProfiles.list,
  });

  const [models, setModels] = useState<ModelInfo[]>([]);

  // 当切换 profile，清掉模型列表（直到下次"获取模型"）
  useEffect(() => {
    setModels([]);
  }, [selectedProfileId]);

  // 自动选首个 profile
  useEffect(() => {
    const list = profilesQuery.data;
    if (list && list.length > 0 && selectedProfileId == null) {
      setSelectedProfileId(list[0].id);
      if (!selectedModel && list[0].default_model) {
        setSelectedModel(list[0].default_model);
      }
    }
  }, [profilesQuery.data, selectedProfileId, selectedModel, setSelectedProfileId, setSelectedModel]);

  const selectedProfile: ApiProfile | undefined = useMemo(
    () => profilesQuery.data?.find((p) => p.id === selectedProfileId),
    [profilesQuery.data, selectedProfileId],
  );

  const createMutation = useMutation({
    mutationFn: (payload: ApiProfileCreate) => endpoints.apiProfiles.create(payload),
    onSuccess: (created) => {
      message.success(`已保存配置：${created.name}`);
      void queryClient.invalidateQueries({ queryKey: ['api-profiles'] });
      setSelectedProfileId(created.id);
      if (created.default_model) setSelectedModel(created.default_model);
      setCreateOpen(false);
      createForm.resetFields();
    },
    onError: (err: unknown) => {
      message.error(err instanceof ApiError ? err.detail : '保存失败');
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: number) => endpoints.apiProfiles.remove(id),
    onSuccess: () => {
      message.success('已删除');
      setSelectedProfileId(null);
      setModels([]);
      void queryClient.invalidateQueries({ queryKey: ['api-profiles'] });
    },
    onError: (err: unknown) => {
      message.error(err instanceof ApiError ? err.detail : '删除失败');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ApiProfileUpdate }) =>
      endpoints.apiProfiles.update(id, payload),
    onSuccess: (updated) => {
      message.success(`已更新配置：${updated.name}`);
      setEditOpen(false);
      editForm.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['api-profiles'] });
    },
    onError: (err: unknown) => {
      message.error(err instanceof ApiError ? err.detail : '更新失败');
    },
  });

  const fetchModelsMutation = useMutation({
    mutationFn: (id: number) => endpoints.apiProfiles.fetchModels(id),
    onSuccess: (resp) => {
      setModels(resp.models);
      if (resp.models.length === 0) {
        message.warning('外部接口返回 0 个模型');
      } else {
        message.success(`成功获取 ${resp.models.length} 个模型`);
        if (!selectedModel || !resp.models.some((m) => m.id === selectedModel)) {
          setSelectedModel(resp.models[0].id);
        }
      }
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.detail : '获取模型失败';
      message.error(msg);
    },
  });

  const baseUrl = selectedProfile?.base_url ?? '';
  const cardClassName = embedded
    ? 'workbench-card api-config-card api-config-card--embedded'
    : 'workbench-card api-config-card';

  return (
    <Card
      size="small"
      className={cardClassName}
      title={
        <Space>
          <span>API 配置</span>
          {selectedProfile && (
            <Tag color="blue" style={{ marginLeft: 4 }}>
              {selectedProfile.name}
            </Tag>
          )}
        </Space>
      }
      extra={
        <Space>
          <Button
            size="small"
            icon={<PlusOutlined />}
            onClick={() => {
              setCreateOpen(true);
              createForm.resetFields();
            }}
          >
            新建配置
          </Button>
          {selectedProfile && (
            <Tooltip title="修改名称、地址、默认模型；如需更换 Key 才填写 Key 字段">
              <Button
                size="small"
                icon={<EditOutlined />}
                onClick={() => {
                  editForm.setFieldsValue({
                    name: selectedProfile.name,
                    base_url: selectedProfile.base_url,
                    default_model: selectedProfile.default_model ?? '',
                    api_key: '',
                  });
                  setEditOpen(true);
                }}
              >
                编辑
              </Button>
            </Tooltip>
          )}
          {selectedProfile && (
            <Popconfirm
              title={`删除配置 "${selectedProfile.name}"？`}
              onConfirm={() => removeMutation.mutate(selectedProfile.id)}
              okText="删除"
              cancelText="取消"
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      }
    >
      {profilesQuery.data && profilesQuery.data.length === 0 ? (
        <Empty description="尚未创建 API 配置，点击右上角“新建配置”">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建第一个配置
          </Button>
        </Empty>
      ) : (
        <Form layout="vertical" size="middle">
          <Row gutter={16}>
            <Col xs={24} md={embedded ? 24 : 12} xl={embedded ? 24 : 12}>
              <Form.Item label="配置选择" tooltip="多套 API 之间切换">
                <Select
                  value={selectedProfileId ?? undefined}
                  onChange={(v) => setSelectedProfileId(v)}
                  placeholder="选择 API 配置"
                  options={(profilesQuery.data ?? []).map((p) => ({
                    value: p.id,
                    label: `${p.name}  (${p.base_url})`,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={embedded ? 24 : 12} xl={embedded ? 24 : 12}>
              <Form.Item label="API 地址">
                <Input value={baseUrl} readOnly placeholder="选择配置后显示" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={embedded ? 24 : 12} xl={embedded ? 24 : 12}>
              <Form.Item label="API Key（已加密存储，仅展示掩码）">
                <Input value={selectedProfile?.api_key_masked ?? ''} readOnly />
              </Form.Item>
            </Col>
            <Col xs={24} md={embedded ? 24 : 12} xl={embedded ? 24 : 12}>
              <Form.Item label="模型">
                <Space.Compact style={{ width: '100%' }}>
                  <Select
                    value={selectedModel ?? undefined}
                    onChange={(v) => setSelectedModel(v)}
                    placeholder={
                      models.length === 0 ? '点击右侧“获取模型”' : '选择模型'
                    }
                    options={
                      models.length > 0
                        ? models.map((m) => ({ value: m.id, label: m.id }))
                        : selectedProfile?.default_model
                          ? [
                              {
                                value: selectedProfile.default_model,
                                label: selectedProfile.default_model,
                              },
                            ]
                          : []
                    }
                    style={{ flex: 1 }}
                  />
                  <Tooltip title="调用 /v1/models 拉取真实可用模型列表">
                    <Button
                      icon={<ReloadOutlined />}
                      loading={fetchModelsMutation.isPending}
                      disabled={!selectedProfileId}
                      onClick={() => {
                        if (selectedProfileId)
                          fetchModelsMutation.mutate(selectedProfileId);
                      }}
                    >
                      获取模型
                    </Button>
                  </Tooltip>
                </Space.Compact>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24}>
              <Form.Item label="图片尺寸" style={{ marginBottom: 0 }}>
                <Select
                  value={selectedSize}
                  onChange={setSelectedSize}
                  options={SIZE_OPTIONS.map((s) => ({ value: s, label: s }))}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      )}

      <Modal
        title="新建 API 配置"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createMutation.isPending}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Form
          form={createForm}
          layout="vertical"
          requiredMark
          onFinish={(values) => {
            createMutation.mutate({
              name: values.name.trim(),
              base_url: values.base_url.trim(),
              api_key: values.api_key,
              default_model: values.default_model?.trim() || null,
            });
          }}
        >
          <Form.Item
            name="name"
            label="配置名称"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input placeholder="例如：local-litellm" autoFocus />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="API 地址（base URL）"
            tooltip="服务前缀；后端会自动拼接 /v1/models、/v1/images/edits 或 /v1/images/generations"
            rules={[
              { required: true, message: '请输入 API 地址' },
              { type: 'url', message: '请输入合法 URL' },
            ]}
          >
            <Input placeholder="http://127.0.0.1:8000" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            tooltip="本地以 Fernet 对称加密存储；获取后保存仅返回掩码"
            rules={[{ required: true, message: '请输入 API Key' }]}
          >
            <Input.Password placeholder="sk-..." autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="default_model"
            label="默认模型（可选）"
            tooltip="不填将以拉取到的列表第一个为默认值"
          >
            <Input placeholder="例如：gpt-image-2" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑 API 配置${selectedProfile ? ` · ${selectedProfile.name}` : ''}`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={() => editForm.submit()}
        confirmLoading={updateMutation.isPending}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Form
          form={editForm}
          layout="vertical"
          requiredMark
          onFinish={(values) => {
            if (!selectedProfile) return;
            const payload: ApiProfileUpdate = {
              name: values.name.trim(),
              base_url: values.base_url.trim(),
              default_model: values.default_model?.trim() || null,
            };
            // 只有当用户重新填了 Key 才发送，避免误清掉
            if (values.api_key && values.api_key.trim()) {
              payload.api_key = values.api_key.trim();
            }
            updateMutation.mutate({ id: selectedProfile.id, payload });
          }}
        >
          <Form.Item
            name="name"
            label="配置名称"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="API 地址（base URL）"
            rules={[
              { required: true, message: '请输入 API 地址' },
              { type: 'url', message: '请输入合法 URL' },
            ]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key（仅在需更换时填写）"
            tooltip="留空表示保持原 Key 不变"
          >
            <Input.Password placeholder="留空则不修改" autoComplete="off" />
          </Form.Item>
          <Form.Item name="default_model" label="默认模型（可选）">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
