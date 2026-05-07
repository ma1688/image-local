// 与后端 Pydantic schemas 对齐
export interface Template {
  id: number;
  code: string;
  name: string;
  prompt_template: string;
  default_model: string | null;
  default_size: string | null;
  builtin: boolean;
  created_at: string;
  /** 模板中出现的所有 {var} 变量（去重，保留首次顺序） */
  placeholders: string[];
  /** 后端目前支持的变量子集之外的变量；UI 上需以 warning 形式提示 */
  unknown_placeholders: string[];
}

export interface TemplateCreate {
  code: string;
  name: string;
  prompt_template?: string;
  default_model?: string | null;
  default_size?: string | null;
}

export interface ApiProfile {
  id: number;
  name: string;
  base_url: string;
  default_model: string | null;
  api_key_masked: string;
  created_at: string;
  updated_at: string;
}

export interface ApiProfileCreate {
  name: string;
  base_url: string;
  api_key: string;
  default_model?: string | null;
}

export interface ApiProfileUpdate {
  name?: string;
  base_url?: string;
  default_model?: string | null;
  /** 空字符串视为不修改 Key */
  api_key?: string;
}

export interface ModelInfo {
  id: string;
  object?: string | null;
  owned_by?: string | null;
}

export interface ModelListResponse {
  models: ModelInfo[];
}

export interface HealthResponse {
  status: string;
  version: string;
  task_backend: string;
  db_ok: boolean;
  redis_ok: boolean;
}

export interface ApiErrorBody {
  detail?: string | Record<string, unknown>;
  [key: string]: unknown;
}

// ===== 图片来源 =====
export interface ImageItem {
  path: string;
  name: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  thumb_url: string;
  valid: boolean;
  reason?: string | null;
}

export interface ScanResponse {
  root: string;
  items: ImageItem[];
  total_seen: number;
  truncated: boolean;
}

export interface UploadResponse {
  upload_dir: string;
  items: ImageItem[];
}

// ===== Jobs =====
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type CandidateStatus = JobStatus;

export interface JobCreate {
  template_code: string;
  api_profile_id: number;
  model: string;
  size: string;
  prompt: string;
  candidates_per_image: number;
  auto_retry: boolean;
  retry_max: number;
  output_dir: string;
  source_paths: string[];
}

export interface JobRead {
  id: number;
  template_code: string;
  api_profile_id: number;
  model: string;
  size: string;
  prompt: string;
  candidates_per_image: number;
  auto_retry: boolean;
  retry_max: number;
  output_dir: string;
  status: JobStatus;
  total_candidates: number;
  succeeded_count: number;
  failed_count: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobCandidateRead {
  id: number;
  job_id: number;
  item_id: number;
  index: number;
  status: CandidateStatus;
  output_path: string | null;
  attempts: number;
  last_error: string | null;
  is_selected: boolean;
  started_at: string | null;
  finished_at: string | null;
}

export interface CandidateSelectRequest {
  is_selected: boolean;
}

export type DownloadScope = 'all' | 'selected';

export interface JobItemRead {
  id: number;
  job_id: number;
  source_path: string;
  source_name: string;
  candidates: JobCandidateRead[];
}

export interface JobDetail extends JobRead {
  items: JobItemRead[];
}

export interface JobListResponse {
  items: JobRead[];
  total: number;
  limit: number;
  offset: number;
}

export interface JobListQuery {
  template_code?: string;
  created_after?: string; // ISO 8601
  created_before?: string;
  limit?: number;
  offset?: number;
}

// ===== Storage / Readiness =====
export type StorageStatus = 'ok' | 'warn' | 'critical';

export interface StorageBucket {
  name: string;
  path: string;
  bytes: number;
  files: number;
}

export interface StorageUsage {
  data_dir: string;
  total_bytes: number;
  buckets: StorageBucket[];
  disk_total_bytes: number;
  disk_free_bytes: number;
  warn_bytes: number;
  hard_limit_bytes: number;
  status: StorageStatus;
}

export interface ReadyCheck {
  ok: boolean;
  detail: string | null;
}

export interface ReadyResponse {
  ready: boolean;
  db: ReadyCheck;
  redis: ReadyCheck;
  fernet: ReadyCheck;
}
