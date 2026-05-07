import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { ImageItem } from '@/api/types';

interface ImageSourceState {
  /** 来源类型：scan(目录扫描) | upload(浏览器上传) */
  sourceType: 'scan' | 'upload';
  /** 上次扫描的目录字符串（持久化） */
  lastScanDir: string;
  /** 当前列表中所有图片（不持久化，启动后清空避免 path 失效） */
  items: ImageItem[];
  /** 选中的 path 集合 */
  selected: Set<string>;
  /** 当前显示的来源描述（host 路径或上传目录） */
  rootLabel: string;

  setSourceType: (t: 'scan' | 'upload') => void;
  setLastScanDir: (d: string) => void;
  setItems: (items: ImageItem[], rootLabel: string) => void;
  toggleSelected: (path: string) => void;
  setSelected: (paths: string[]) => void;
  selectAllValid: () => void;
  clearAll: () => void;
}

export const useImageSourceStore = create<ImageSourceState>()(
  persist(
    (set, get) => ({
      sourceType: 'scan',
      lastScanDir: '',
      items: [],
      selected: new Set<string>(),
      rootLabel: '',
      setSourceType: (t) => set({ sourceType: t }),
      setLastScanDir: (d) => set({ lastScanDir: d }),
      setItems: (items, rootLabel) => {
        const validPaths = items.filter((i) => i.valid).map((i) => i.path);
        set({
          items,
          rootLabel,
          selected: new Set(validPaths), // 默认全选 valid
        });
      },
      toggleSelected: (path) => {
        const s = new Set(get().selected);
        if (s.has(path)) s.delete(path);
        else s.add(path);
        set({ selected: s });
      },
      setSelected: (paths) => set({ selected: new Set(paths) }),
      selectAllValid: () => {
        const s = new Set(get().items.filter((i) => i.valid).map((i) => i.path));
        set({ selected: s });
      },
      clearAll: () => set({ items: [], selected: new Set<string>(), rootLabel: '' }),
    }),
    {
      name: 'local-image:image-source',
      storage: createJSONStorage(() => localStorage),
      version: 1,
      // 只持久化目录字符串与来源类型，items / selected 等运行时状态不持久化
      partialize: (s) => ({ sourceType: s.sourceType, lastScanDir: s.lastScanDir }),
    },
  ),
);
