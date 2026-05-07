import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface WorkbenchState {
  /** 当前选中的流程模板 code */
  templateCode: string;
  /** 用户输入的提示词（与模板 prompt_template 拼接） */
  prompt: string;
  setTemplateCode: (c: string) => void;
  setPrompt: (s: string) => void;
}

export const useWorkbenchStore = create<WorkbenchState>()(
  persist(
    (set) => ({
      templateCode: 'ref_batch',
      prompt: '',
      setTemplateCode: (c) => set({ templateCode: c }),
      setPrompt: (s) => set({ prompt: s }),
    }),
    {
      name: 'local-image:workbench',
      storage: createJSONStorage(() => localStorage),
      version: 1,
    },
  ),
);
