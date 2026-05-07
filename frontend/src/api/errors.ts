import { ApiError } from './client';

/**
 * 把任意错误对象转成"面向用户"的中文短句。
 *
 * 设计：
 * - HTTP 状态码语义优先：401 / 403 / 404 / 409 / 413 / 415 / 422 / 429 / 5xx 都有
 *   清晰的话术；其他状态码兜底"请求失败：<原始信息>"。
 * - 网络层错误（CORS / fetch failed / Aborted）走专门分支。
 * - 输出始终保留"原始 detail"作为副信息（前端自行决定 UI 是否显示）。
 */
export interface UiError {
  /** 给用户看的标题，例如"API Key 无效" */
  title: string;
  /** 详情，原始 detail / message，用于辅助排查 */
  detail: string;
  /** Antd message 推荐级别，warning 表示用户可继续操作 */
  level: 'error' | 'warning';
}

export function errorToUi(err: unknown): UiError {
  if (err instanceof ApiError) {
    const detail = err.detail || `HTTP ${err.status}`;
    switch (err.status) {
      case 400:
        return { title: detail || '请求参数有误', detail, level: 'warning' };
      case 401:
        return {
          title: 'API Key 无效或缺失',
          detail,
          level: 'error',
        };
      case 403:
        return {
          title: '没有访问权限或路径不在白名单',
          detail,
          level: 'error',
        };
      case 404:
        return { title: '资源不存在', detail, level: 'warning' };
      case 409:
        return { title: '资源冲突（重复或状态不允许）', detail, level: 'warning' };
      case 413:
        return {
          title: '上传内容过大',
          detail,
          level: 'error',
        };
      case 415:
        return { title: '不支持的文件格式', detail, level: 'error' };
      case 422:
        return { title: '请求字段校验失败', detail, level: 'warning' };
      case 429:
        return {
          title: '请求过于频繁，请稍后再试',
          detail,
          level: 'warning',
        };
      case 503:
        return { title: '依赖服务暂不可用', detail, level: 'error' };
      default:
        if (err.status >= 500) {
          return {
            title: '服务异常，请重试或查看日志',
            detail,
            level: 'error',
          };
        }
        return { title: detail, detail, level: 'error' };
    }
  }
  if (err instanceof DOMException && err.name === 'AbortError') {
    return { title: '请求已取消', detail: err.message, level: 'warning' };
  }
  if (err instanceof TypeError) {
    // fetch 网络层错误（CORS / DNS / 断网）通常是 TypeError: Failed to fetch
    return {
      title: '无法连接服务，检查网络或后端是否可达',
      detail: err.message,
      level: 'error',
    };
  }
  if (err instanceof Error) {
    return { title: err.message || '操作失败', detail: err.message, level: 'error' };
  }
  return { title: '未知错误', detail: String(err), level: 'error' };
}
