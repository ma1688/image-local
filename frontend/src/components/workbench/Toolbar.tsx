import { Card, Tag, Tooltip, Typography } from 'antd';
import { ApartmentOutlined, FolderOpenOutlined, ApiOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';
import { useConfigStore } from '@/store/configStore';
import { useWorkbenchStore } from '@/store/workbenchStore';

const { Text } = Typography;

export default function Toolbar() {
  const templateCode = useWorkbenchStore((s) => s.templateCode);
  const outputDir = useConfigStore((s) => s.outputDir);
  const selectedProfileId = useConfigStore((s) => s.selectedProfileId);

  const templatesQuery = useQuery({
    queryKey: ['templates'],
    queryFn: endpoints.templates.list,
  });
  const profilesQuery = useQuery({
    queryKey: ['api-profiles'],
    queryFn: endpoints.apiProfiles.list,
  });

  const template = templatesQuery.data?.find((t) => t.code === templateCode);
  const profile = profilesQuery.data?.find((p) => p.id === selectedProfileId);
  const requestUrl = profile?.base_url
    ? `${profile.base_url.replace(/\/$/, '')}/v1/images/generations`
    : '尚未选择 API 配置';

  return (
    <Card
      size="small"
      className="workbench-card workbench-card--compact workbench-toolbar"
    >
      <div className="workbench-toolbar__grid">
        <div className="toolbar-chip">
          <ApartmentOutlined className="toolbar-chip__icon toolbar-chip__icon--blue" />
          <Text className="toolbar-chip__label">当前流程：</Text>
          <div className="toolbar-chip__value">
            <Tag color="blue" style={{ marginInlineEnd: 0 }}>
              {template?.name ?? '未选择'}
            </Tag>
          </div>
        </div>
        <div className="toolbar-chip">
          <FolderOpenOutlined className="toolbar-chip__icon toolbar-chip__icon--slate" />
          <Text className="toolbar-chip__label">输出目录：</Text>
          <div className="toolbar-chip__value">
            <Tooltip title={outputDir}>
              <Text ellipsis className="toolbar-chip__path">
                {outputDir}
              </Text>
            </Tooltip>
          </div>
        </div>
        <div className="toolbar-chip">
          <ApiOutlined className="toolbar-chip__icon toolbar-chip__icon--violet" />
          <Text className="toolbar-chip__label">实际请求接口地址：</Text>
          <div className="toolbar-chip__value">
            <Tooltip title={requestUrl}>
              <Text ellipsis className="toolbar-chip__path toolbar-chip__path--link">
                {requestUrl}
              </Text>
            </Tooltip>
          </div>
        </div>
      </div>
    </Card>
  );
}
