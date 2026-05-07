export interface ApiResponse<TData> {
  success: boolean;
  message: string;
  data: TData | null;
}

export interface LoginRequest {
  email: string;
  password: string;
  sessionId?: string;
  forceRelogin?: boolean;
}

export interface LoginResponse extends ApiResponse<null> {
  session_id: string | null;
  state_path: string | null;
  email?: string | null;
  login_step?: "success" | "need_otp" | "error";
  need_otp?: boolean;
  checkpoint_url?: string | null;
}

export interface VerifyLoginRequest {
  sessionId: string;
  otp: string;
  checkpointUrl?: string;
}

export type VerifyLoginResponse = LoginResponse;

export interface StartWorkflowRequest {
  email: string;
  password: string;
  force_relogin?: boolean;
  max_posts?: number;
  target_date?: string;
  mode?: "Detailed" | "Fast";
  delay_sec?: number;
  group_urls?: string[];
}

export interface StartWorkflowResponseData {
  http_status?: number;
  response_preview?: string;
  response_message?: string;
  response_payload?: unknown;
  id_session_crawl?: string;
}

export type StartWorkflowResponse = ApiResponse<StartWorkflowResponseData | null>;

export interface CrawlGroupRequest {
  sessionId?: string;
  email?: string;
  groupUrl: string;
  maxItems?: number;
  targetDate?: string;
}

export interface TopPostResponse {
  author: string;
  content: string;
  posted_at_raw: string;
  posted_at: string | null;
  likes: number;
  comments: number;
  reposts: number;
  score: number;
  post_url: string;
}

export interface CrawlDataResponse {
  session_id: string;
  group_url: string;
  group_name: string;
  target_date: string;
  email?: string | null;
  total_posts_scraped: number;
  total_posts_in_target_date: number;
  top_post: TopPostResponse | null;
}

export type CrawlResponse = ApiResponse<CrawlDataResponse>;

/** Chỉ gửi một mode: `preset` HOẶC `date_from`/`date_to` HOẶC `date` (một ngày) — khớp backend. */
export type FilterDatePreset = "last_7_days" | "last_30_days";

export interface FilterDataRequest {
  email: string;
  /** Một ngày cụ thể (YYYY-MM-DD) — mode single */
  date?: string;
  /** Khoảng ngày — mode range (backend cho phép chỉ một trong hai, còn thiếu sẽ lấy hôm nay hoặc = đầu kia) */
  date_from?: string;
  date_to?: string;
  preset?: FilterDatePreset;
}

/** Một lần cào — khớp backend (gom ``posts`` trong phiên). */
export interface CrawlSessionGroup {
  id_session_crawl: string;
  group_name: string;
  group_url: string;
  email_crawl: string;
  posts_count: number;
  posts: Array<Record<string, unknown>>;
}

/** ``data`` = ``CrawlSessionGroup[]`` — phiên mới nhất trước. */
export type FilterDataResponse = ApiResponse<CrawlSessionGroup[] | null>;

export interface GetAllPostsRequest {
  email: string;
  filters?: Record<string, unknown>;
}

export type GetAllPostsResponse = ApiResponse<CrawlSessionGroup[] | null>;

/** Payload trả về từ backend sau khi gọi webhook n8n (nhóm). */
export interface N8nGroupWebhookResultData {
  http_status?: number;
  response_preview?: string;
  parsed?: unknown;
  total?: number;
  groups?: N8nManagedGroup[];
}

export type N8nGroupOperationResponse = ApiResponse<N8nGroupWebhookResultData | null>;

export interface N8nManagedGroup {
  row_number: number | null;
  url_group: string;
  name_group: string;
  email: string;
  member: number;
}

export interface GetAllN8nGroupsRequest {
  email: string;
}

export interface AddN8nGroupRequest {
  url_group: string;
  name_group: string;
  member: number;
  email?: string;
}

export interface RemoveN8nGroupRequest {
  url_group: string;
  email?: string;
}

export interface UpdateN8nGroupRequest {
  url_group_need_update: string;
  name_group: string;
  member: number;
  new_url_group?: string | null;
  new_name_group?: string | null;
  new_member?: number | null;
  email?: string;
}

export interface StatusDataResponse {
  api_key_enabled: boolean;
  headless: boolean;
  default_max_items: number;
  default_scroll_times: number;
  cors_origins: string[];
  n8n_webhook_configured: boolean;
  n8n_get_link_webhook_configured: boolean;
  n8n_webhook_get_post_crawled_configured: boolean;
  n8n_webhook_get_url_group_crawled_configured: boolean;
  n8n_webhook_get_result_crawl_by_id_configured: boolean;
  n8n_webhook_filter_data_configured: boolean;
  n8n_webhook_get_all_posts_configured: boolean;
  n8n_webhook_get_group_configured?: boolean;
  n8n_webhook_add_group_configured?: boolean;
  n8n_webhook_remove_group_configured?: boolean;
  n8n_webhook_update_group_configured?: boolean;
}

export type StatusResponse = ApiResponse<StatusDataResponse>;
