import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface ConfigState {
  selectedProfileId: number | null;
  selectedModel: string | null;
  selectedSize: string;
  outputDir: string;
  candidatesPerImage: number;
  retryMax: number;
  autoRetry: boolean;
  setSelectedProfileId: (id: number | null) => void;
  setSelectedModel: (m: string | null) => void;
  setSelectedSize: (s: string) => void;
  setOutputDir: (d: string) => void;
  setCandidatesPerImage: (n: number) => void;
  setRetryMax: (n: number) => void;
  setAutoRetry: (v: boolean) => void;
}

export const useConfigStore = create<ConfigState>()(
  persist(
    (set) => ({
      selectedProfileId: null,
      selectedModel: null,
      selectedSize: '1024x1024',
      outputDir: 'data/outputs',
      candidatesPerImage: 3,
      retryMax: 1,
      autoRetry: true,
      setSelectedProfileId: (id) => set({ selectedProfileId: id }),
      setSelectedModel: (m) => set({ selectedModel: m }),
      setSelectedSize: (s) => set({ selectedSize: s }),
      setOutputDir: (d) => set({ outputDir: d }),
      setCandidatesPerImage: (n) => set({ candidatesPerImage: n }),
      setRetryMax: (n) => set({ retryMax: n }),
      setAutoRetry: (v) => set({ autoRetry: v }),
    }),
    {
      name: 'local-image:config',
      storage: createJSONStorage(() => localStorage),
      version: 1,
    },
  ),
);
