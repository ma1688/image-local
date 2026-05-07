import { api } from './client';
import type {
  ApiProfile,
  ApiProfileCreate,
  ApiProfileUpdate,
  CandidateSelectRequest,
  DownloadScope,
  HealthResponse,
  JobCandidateRead,
  JobCreate,
  JobDetail,
  JobListQuery,
  JobListResponse,
  JobRead,
  ModelListResponse,
  ScanResponse,
  Template,
  TemplateCreate,
  UploadResponse,
} from './types';

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';

export const endpoints = {
  health: () => api.get<HealthResponse>('/health'),

  templates: {
    list: () => api.get<Template[]>('/templates'),
    create: (payload: TemplateCreate) => api.post<Template>('/templates', payload),
  },

  apiProfiles: {
    list: () => api.get<ApiProfile[]>('/api-profiles'),
    create: (payload: ApiProfileCreate) => api.post<ApiProfile>('/api-profiles', payload),
    update: (id: number, payload: ApiProfileUpdate) =>
      api.patch<ApiProfile>(`/api-profiles/${id}`, payload),
    remove: (id: number) => api.delete<void>(`/api-profiles/${id}`),
    fetchModels: (id: number) => api.post<ModelListResponse>(`/api-profiles/${id}/models`),
  },

  jobs: {
    submit: (payload: JobCreate) => api.post<JobRead>('/jobs', payload),
    get: (id: number) => api.get<JobDetail>(`/jobs/${id}`),
    list: (q?: JobListQuery) => {
      const params = new URLSearchParams();
      if (q?.template_code) params.set('template_code', q.template_code);
      if (q?.created_after) params.set('created_after', q.created_after);
      if (q?.created_before) params.set('created_before', q.created_before);
      if (typeof q?.limit === 'number') params.set('limit', String(q.limit));
      if (typeof q?.offset === 'number') params.set('offset', String(q.offset));
      const qs = params.toString();
      return api.get<JobListResponse>(`/jobs${qs ? `?${qs}` : ''}`);
    },
    cancel: (id: number) => api.post<JobRead>(`/jobs/${id}/cancel`),
    retryFailed: (id: number) => api.post<JobRead>(`/jobs/${id}/retry-failed`),
    remove: (id: number) => api.delete<void>(`/jobs/${id}`),
    selectCandidate: (
      jobId: number,
      candidateId: number,
      payload: CandidateSelectRequest,
    ) =>
      api.patch<JobCandidateRead>(
        `/jobs/${jobId}/candidates/${candidateId}/select`,
        payload,
      ),
    /** 直接生成下载链接，前端用 location.href / a[href] 触发浏览器另存 */
    downloadUrl: (jobId: number, scope: DownloadScope = 'all') =>
      `${API_BASE}/jobs/${jobId}/download?scope=${scope}`,
  },

  images: {
    scan: (dir: string, recursive = false) =>
      api.post<ScanResponse>('/images/scan', { dir, recursive }),
    upload: async (files: File[]): Promise<UploadResponse> => {
      const fd = new FormData();
      for (const f of files) fd.append('files', f, f.name);
      const resp = await fetch(`${API_BASE}/images/upload`, {
        method: 'POST',
        body: fd,
      });
      const text = await resp.text();
      const parsed = text ? (JSON.parse(text) as unknown) : null;
      if (!resp.ok) {
        const detail =
          parsed && typeof parsed === 'object' && 'detail' in parsed
            ? String((parsed as { detail: unknown }).detail)
            : `HTTP ${resp.status}`;
        throw new Error(detail);
      }
      return parsed as UploadResponse;
    },
  },
};
