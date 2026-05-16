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

export type StartWorkflowResponse =
  ApiResponse<StartWorkflowResponseData | null>;

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

export type N8nGroupOperationResponse =
  ApiResponse<N8nGroupWebhookResultData | null>;

export interface N8nManagedGroup {
  row_number: number | null;
  url_group: string;
  name_group: string;
  email: string;
  member: number;
  type: string;
}

export interface GetAllN8nGroupsRequest {
  email: string;
}

export interface AddN8nGroupRequest {
  url_group: string;
  name_group: string;
  member: number;
  email?: string;
  type?: string;
}

/** POST /groups/add-list-group */
export interface AddListGroupRequest {
  group_urls: string[];
  email?: string;
  type?: string;
  post_to_webhook?: boolean;
  delay_min_sec?: number;
  delay_max_sec?: number;
  webhook_timeout_sec?: number;
}

export interface BulkGroupImportScrapedItem {
  url_group: string;
  name_group: string;
  member: number;
  memberCount: number | null;
  success: boolean;
  error: string | null;
}

export interface BulkGroupImportData {
  items: BulkGroupImportScrapedItem[];
  webhook_http_status?: number | null;
  webhook_response_preview?: string | null;
  webhook_response?: unknown;
  webhook_skipped: boolean;
}

export type BulkGroupImportResponse = ApiResponse<BulkGroupImportData | null>;

/** POST /linkedin/me/profile-slug-sheet-check */
export interface ProfileSlugSheetCheckData {
  email_found_in_sheet: boolean;
  webhook_http_status: number;
  row_count: number;
  matched_profile_slug?: string | null;
}

export type ProfileSlugSheetCheckResponse =
  ApiResponse<ProfileSlugSheetCheckData | null>;

/** POST /linkedin/me/ensure-profile-slug */
export interface EnsureProfileSlugData {
  email_found_in_sheet?: boolean;
  skipped_playwright?: boolean;
  skipped_register_webhook?: boolean;
  sheet_check_skipped_no_webhook?: boolean;
  profile_slug?: string | null;
  profile_url?: string | null;
  sheet_webhook_http_status?: number | null;
  register_webhook_http_status?: number | null;
}

export type EnsureProfileSlugResponse =
  ApiResponse<EnsureProfileSlugData | null>;

/** POST /linkedin/me/profile-slug — slug public ``/in/<slug>`` của tài khoản đang đăng nhập (Playwright). */
export interface GetMyProfileSlugData {
  profile_slug: string;
  profile_url: string;
  session_id: string;
}

export type GetMyProfileSlugResponse = ApiResponse<GetMyProfileSlugData | null>;

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
  new_type?: string | null;
  email?: string;
}

export interface LinkedinAppStatsRequest {
  email: string;
}

export interface LinkedinAppStatsData {
  total_comments: number;
  total_interactions: number;
  total_posts_crawled: number;
}

export type LinkedinAppStatsResponse = ApiResponse<LinkedinAppStatsData | null>;

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
  n8n_webhook_add_list_group_configured?: boolean;
  /** @deprecated Cùng giá trị với n8n_webhook_add_list_group_configured */
  n8n_webhook_bulk_import_groups_configured?: boolean;
  n8n_webhook_get_profile_slugs_configured?: boolean;
  n8n_webhook_add_profile_slug_configured?: boolean;
  n8n_webhook_post_reaction_configured?: boolean;
  n8n_webhook_post_comment_configured?: boolean;
  n8n_webhook_assign_kpi_configured?: boolean;
  n8n_webhook_check_permission_configured?: boolean;
}

export type StatusResponse = ApiResponse<StatusDataResponse>;

/** POST /linkedin/post/react — khớp backend ``PostReactionKind``. */
export type PostLinkedInReactionKind =
  | "like"
  | "love"
  | "celebrate"
  | "support"
  | "insightful"
  | "funny";

export interface PostLinkedInReactionRequest {
  post_url: string;
  reaction: PostLinkedInReactionKind;
  Email_crawl: string;
  ID_session_crawl: string;
  row_number: number;
  /** Toàn bộ trường dòng (sheet/API) — webhook merge rồi ghi đè id + reaction + post_url. */
  sheet_row?: Record<string, unknown> | null;
  session_id?: string | null;
  email?: string | null;
  post_to_webhook?: boolean;
  /** Gỡ reaction trên LinkedIn và ghi ô reaction trống (không null) trên sheet. */
  clear_reaction?: boolean;
}

export interface PostLinkedInReactionData {
  reaction: string;
  row_number: number;
  Email_crawl: string;
  ID_session_crawl: string;
  post_url: string;
  final_url: string;
  resolved_playwright_session_id: string;
  webhook_called: boolean;
  webhook_http_status?: number | null;
  webhook_response_preview?: string | null;
  playwright_skipped?: boolean;
  synced_row_count?: number;
  webhook_sync_success_count?: number;
}

export type PostLinkedInReactionResponse =
  ApiResponse<PostLinkedInReactionData | null>;

/** Một phần tử trong mảng ``comment`` — POST /linkedin/post/comment. */
export interface LinkedInAppCommentEntry {
  comment_content: string;
  "ngày comment": string;
}

export interface PostLinkedInCommentRequest {
  post_url: string;
  comment_text: string;
  Email_crawl: string;
  ID_session_crawl: string;
  row_number: number;
  /** Lịch sử comment đã gửi (backend append phần tử mới). */
  existing_app_comments: LinkedInAppCommentEntry[];
  sheet_row?: Record<string, unknown> | null;
  session_id?: string | null;
  email?: string | null;
  post_to_webhook?: boolean;
  typing_delay_ms?: number;
  timeout_ms?: number;
}

export interface PostLinkedInCommentData {
  comment_text: string;
  app_comments: LinkedInAppCommentEntry[];
  row_number: number;
  Email_crawl: string;
  ID_session_crawl: string;
  post_url: string;
  final_url: string;
  resolved_playwright_session_id: string;
  webhook_called: boolean;
  webhook_http_status?: number | null;
  webhook_response_preview?: string | null;
  synced_row_count?: number;
  webhook_sync_success_count?: number;
}

export type PostLinkedInCommentResponse =
  ApiResponse<PostLinkedInCommentData | null>;

export interface PostLinkedInCommentDeleteData {
  comment_text: string;
  row_number: number;
  Email_crawl: string;
  ID_session_crawl: string;
  post_url: string;
  final_url: string;
  resolved_playwright_session_id: string;
  webhook_called: boolean;
  webhook_http_status?: number | null;
  webhook_response_preview?: string | null;
  synced_row_count?: number;
  webhook_sync_success_count?: number;
}

export type PostLinkedInCommentDeleteResponse =
  ApiResponse<PostLinkedInCommentDeleteData | null>;

export interface PostLinkedInCommentEditData {
  old_comment_text: string;
  new_comment_text: string;
  row_number: number;
  Email_crawl: string;
  ID_session_crawl: string;
  post_url: string;
  final_url: string;
  resolved_playwright_session_id: string;
  webhook_called: boolean;
  webhook_http_status?: number | null;
  webhook_response_preview?: string | null;
  synced_row_count?: number;
  webhook_sync_success_count?: number;
}

export type PostLinkedInCommentEditResponse =
  ApiResponse<PostLinkedInCommentEditData | null>;

/** POST /linkedin/post/sync-progress */
export interface SyncPostProgressRequest {
  post_url: string;
  profile_slug: string;
  Email_crawl: string;
  ID_session_crawl: string;
  row_number: number;
  sheet_row?: Record<string, unknown> | null;
  session_id?: string | null;
  email?: string | null;
  post_to_webhook?: boolean;
  timeout_ms?: number;
}

export interface SyncPostProgressData {
  post_url: string;
  reaction: string | null;
  comments: LinkedInAppCommentEntry[];
  total_reactions?: number;
  total_comments?: number;
  row_number?: number;
  webhook_called: boolean;
  webhook_http_status?: number | null;
  webhook_response_preview?: string | null;
}

export type SyncPostProgressResponse = ApiResponse<SyncPostProgressData | null>;

/** POST /linkedin/sync-all-progress */
export interface SyncAllProgressRequest {
  email_crawl: string;
  profile_slug: string;
  session_id?: string | null;
  email?: string | null;
  timeout_ms_per_post?: number;
  limit_posts?: number;
}

export interface SyncAllProgressData {
  posts_attempted: number;
  posts_succeeded: number;
  details: SyncPostProgressData[];
}

export type SyncAllProgressResponse = ApiResponse<SyncAllProgressData | null>;

export interface KpiItem {
  start_day: string;
  end_day: string;
  total_reaction: string | number;
  total_comment: string | number;
  total_post_crawl: string | number;
  total_session_crawl: string | number;
}

export interface AssignKpiRequest {
  leader_role: string;
  role: string;
  email: string;
  profile_slug: string;
  email_leader: string;
  kpi: KpiItem[];
}

export interface CheckPermissionRequest {
  email: string;
}

export interface CheckPermissionData {
  permission: boolean;
}

export type CheckPermissionResponse = ApiResponse<CheckPermissionData | null>;

export interface GetAllKpiRequest {
  email_leader: string;
}

export interface GetKpiByEmailRequest {
  email: string;
}

export interface AddMemberRequest {
  email_member: string;
  email_leader: string;
}

export interface GetProfilesRequest {
  email: string;
}

export interface UpdateProfileSlugRequest {
  email_crawl: string;
  profile_slug: string;
  profile_url: string;
  role: string;
  kpi: any[];
  email_leader?: string;
}

export interface VerifyLeaderCodeRequest {
  code: string;
}

export interface KpiMemberData {
  email: string;
  role: string;
  profile_slug?: string;
  email_leader?: string;
  kpi: any[];
}

export interface GetAllKpiResponse extends ApiResponse<KpiMemberData[]> {
  total: number;
}

export interface GetKpiByEmailResponse extends ApiResponse<KpiMemberData[]> {
  total: number;
}
