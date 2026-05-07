import type { MessageInstance } from 'antd/es/message/interface';
import { errorToUi } from './errors';

/**
 * 把任意错误推到 Antd `message` 实例，按 errorToUi 给出的 level 选择 error / warning。
 * 详情在控制台 console.error，避免把过长的 detail 全部塞到 toast。
 */
export function notifyError(message: MessageInstance, err: unknown): void {
  const ui = errorToUi(err);
  if (ui.level === 'warning') {
    void message.warning(ui.title);
  } else {
    void message.error(ui.title);
  }
  if (ui.detail && ui.detail !== ui.title) {
    console.error('[notifyError]', ui.title, '|', ui.detail);
  }
}
