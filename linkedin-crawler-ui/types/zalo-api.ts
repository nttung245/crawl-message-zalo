export type ZaloAuthStatus =
  | "waiting_scan"
  | "confirmed"
  | "qr_expired"
  | "session_expired"
  | "not_logged_in";

export type ZaloJobStatus = "queued" | "running" | "completed" | "failed";

export interface ZaloAuthInitResponse {
  session_id: string;
  qr_base64: string;
  status: ZaloAuthStatus;
  expires_in: number;
}

export interface ZaloAuthStatusResponse {
  session_id: string;
  status: ZaloAuthStatus;
}

export interface ZaloCurrentStatusResponse {
  user_id: string;
  session_id: string | null;
  status: ZaloAuthStatus;
  is_logged_in: boolean;
  can_crawl: boolean;
  session_expired?: boolean;
  login_url: string | null;
  manual_viewer_url?: string | null;
  qr_base64?: string | null;
}

export interface ZaloManualLoginResponse {
  session_id: string;
  status: ZaloAuthStatus;
  can_crawl: boolean;
  manual_viewer_url?: string | null;
}

export interface ZaloDeleteSessionResponse {
  message: string;
}

export type ZaloWorkerStatus = "online" | "degraded" | "offline" | "unknown";

export interface ZaloWorkerInfo {
  id: string;
  label: string;
  status: ZaloWorkerStatus | string;
  is_default: boolean;
  queue_state: string;
}

export interface ZaloWorkersResponse {
  workers: ZaloWorkerInfo[];
  selected_worker_id: string | null;
}

export interface ZaloAccountInfo {
  account_id: string;
  owner_id?: string | null;
  label: string;
  phone?: string | null;
  status?: string | null;
  is_active?: boolean;
  has_auth?: boolean;
  listener?: {
    running: boolean;
    connected: boolean;
    pid?: number | null;
    last_event_at?: string | null;
    last_error?: string | null;
    messages_seen?: number;
    auth_expired?: boolean;
  };
}

export interface ZaloAccountsResponse {
  owner_id: string;
  accounts: ZaloAccountInfo[];
}

export interface ZaloInboxReportAccount {
  account_id: string;
  label: string;
  owner_id: string;
  message_count: number;
  customer_count: number;
  latest_message_at?: string | null;
}

export interface ZaloInboxReportCustomer {
  account_id: string;
  account_label: string;
  customer_id: string;
  customer_name: string;
  conversation_id?: string | null;
  conversation_name?: string | null;
  message_count: number;
  sent_count: number;
  received_count: number;
  latest_message_at?: string | null;
  latest_content?: string | null;
}

export interface ZaloInboxReportResponse {
  accounts: ZaloInboxReportAccount[];
  customers: ZaloInboxReportCustomer[];
  total_messages: number;
  total_customers: number;
}

export interface ZaloConversationSummary {
  conversation_id: string;
  conversation_name: string;
  account_id: string;
  message_count: number;
  image_count: number;
  sent_count: number;
  received_count: number;
  latest_message_at?: string | null;
  latest_content?: string | null;
  latest_sender_name?: string | null;
  has_messages?: boolean;
  sync_status?: "has_messages" | "known_empty" | string;
  avatar_url?: string | null;
  unread_count?: number;
  is_pinned?: boolean;
}

export interface ZaloConversationListResponse {
  account_id: string;
  conversations: ZaloConversationSummary[];
  total: number;
}

export interface ZaloSyncRecentGroupResult {
  group_id: string;
  group_name: string;
  messages_saved: number;
  status: "has_messages" | "empty" | "error" | string;
  error?: string | null;
}

export interface ZaloSyncRecentResponse {
  account_id: string;
  scanned: number;
  groups_with_messages: number;
  messages_saved: number;
  errors: number;
  results: ZaloSyncRecentGroupResult[];
}

export interface ZaloStartCrawlRequest {
  sessionId?: string | null;
  userId?: string;
  group_name: string;
  group_id?: string | null;
  sheet_tab?: string;
  max_messages?: number;
}

export interface ZaloStartCrawlResponse {
  job_id: string;
  status: "queued" | "running";
  sheet_url: string | null;
}

export interface ZaloCrawledGroupItem {
  group_name: string;
  sheet_tab: string;
  message_count: number;
}

export interface ZaloCrawledGroupsResponse {
  sheet_id: string;
  sheet_url: string;
  total_groups: number;
  groups: ZaloCrawledGroupItem[];
}

export interface ZaloJobProgress {
  messages_collected: number;
  images_found: number;
  oldest_message_date: string | null;
}

export interface ZaloMessage {
  id?: string | number;
  sender: string;
  time_text: string;
  is_sent?: boolean;
  content: string;
  image_urls?: string[];
}

export interface ZaloJobData {
  job_id: string;
  user_id?: string;
  group_id?: string | null;
  group_name: string;
  sheet_id?: string | null;
  sheet_tab?: string | null;
  status: ZaloJobStatus;
  progress: ZaloJobProgress;
  started_at: string;
  completed_at?: string | null;
  error?: string | null;
  sheet_url?: string | null;
  messages?: ZaloMessage[] | null;
}

export interface ZaloStoredAsset {
  id?: string;
  message_id?: string | null;
  source_url?: string | null;
  storage_path?: string | null;
  storage_url?: string | null;
  status: "pending" | "uploaded" | "failed" | string;
  error?: string | null;
}

export interface ZaloLibraryMessage {
  id: string;
  user_id: string;
  job_id?: string | null;
  group_id?: string | null;
  group_name?: string | null;
  source_message_id?: string | null;
  sender_id?: string | null;
  sender_name?: string | null;
  timestamp_text?: string | null;
  time_text?: string | null;
  type: string;
  content?: string | null;
  is_sent: boolean;
  is_deleted: boolean;
  assets: ZaloStoredAsset[];
}

export type ZaloLibraryContentKind = "all" | "text" | "image";

export interface ZaloLibraryGroupSummary {
  group_name: string;
  sheet_tab?: string | null;
  message_count: number;
  image_count: number;
  latest_message_at?: string | null;
}

export interface ZaloLibraryListResponse {
  messages: ZaloLibraryMessage[];
  groups: ZaloLibraryGroupSummary[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface ZaloLibraryBulkDeleteRequest {
  message_ids?: string[];
  group_name?: string;
  delete_all_matching?: boolean;
}

export interface ZaloLibraryBulkDeleteResponse {
  deleted_count: number;
}

export interface ZaloLibraryMessageCreateRequest {
  group_name?: string;
  sender_name?: string;
  time_text?: string;
  type?: string;
  content?: string;
  asset_urls?: string[];
}

export interface ZaloLibraryMessageUpdateRequest {
  group_name?: string;
  sender_name?: string;
  time_text?: string;
  type?: string;
  content?: string;
  is_deleted?: boolean;
}

export interface ZaloLiveGroup {
  group_id: string | null;
  name: string;
  avatar_url?: string | null;
  last_message?: string | null;
  unread_count: number;
}

export type ZaloGroupVerifyStatus =
  | "unchecked"
  | "verified"
  | "not_found"
  | "personal_chat"
  | "zalo_not_ready"
  | "message_panel_missing"
  | "duplicate"
  | "failed";

export interface ZaloVerifyGroupRequestItem {
  group_name: string;
  group_id?: string | null;
  sheet_tab?: string | null;
}

export interface ZaloVerifiedGroupItem {
  group_name: string;
  group_id?: string | null;
  sheet_tab?: string | null;
  current_title?: string | null;
  member_count?: number | null;
  message_count: number;
  warnings: string[];
}

export interface ZaloRejectedGroupItem {
  group_name: string;
  group_id?: string | null;
  reason: ZaloGroupVerifyStatus | string;
  detail: string;
  current_title?: string | null;
  member_count?: number | null;
  warnings: string[];
}

export interface ZaloVerifyGroupsResponse {
  verified: ZaloVerifiedGroupItem[];
  rejected: ZaloRejectedGroupItem[];
}

export type ZaloBroadcastContentMode = "text" | "image" | "both";

export interface ZaloBroadcastTarget {
  group_id?: string | null;
  group_name: string;
}

export interface ZaloBroadcastRequest {
  user_id?: string;
  message_ids: string[];
  targets: ZaloBroadcastTarget[];
  content_mode: ZaloBroadcastContentMode;
}

export interface ZaloBroadcastPreviewItem {
  message_id: string;
  content?: string | null;
  image_count: number;
  image_urls?: string[];
  send_text: boolean;
  send_images: boolean;
  warnings: string[];
}

export interface ZaloBroadcastPreviewResponse {
  target_count: number;
  message_count: number;
  items: ZaloBroadcastPreviewItem[];
  warnings: string[];
}

export interface ZaloBroadcastResponse {
  campaign_id: string;
  status: string;
}

export interface ZaloBroadcastStatusResponse {
  campaign: Record<string, unknown>;
  targets: Record<string, unknown>[];
  items: Record<string, unknown>[];
  logs: Record<string, unknown>[];
}

// Agent Test Extract Types
export interface AgentTestExtractRequest {
  group_name?: string;
  texts?: string[];
  stream?: boolean;
  timeout?: number;
}

export interface AgentTestProgress {
  completed: number;
  total: number;
  extracted: number;
  not_listing: number;
  failed: number;
}

export interface AgentTestListing {
  apartment_name?: string | null;
  district?: string | null;
  address?: string | null;
  bedrooms?: number | null;
  price_vnd?: number | null;
  area_m2?: number | null;
  contact_phone?: string | null;
  contact_zalo?: string | null;
  image_count: number;
  images: string[];
  raw_text: string;
  source_message_ids: string[];
}

export interface AgentTestExtractResult {
  raw_message_id: string;
  raw_text: string;
  status: "extracted" | "not_listing" | "failed";
  listing?: AgentTestListing | null;
  error_message?: string | null;
  source_message_ids: string[];
}

export interface AgentTestExtractResponse {
  total: number;
  extracted: number;
  not_listing: number;
  failed: number;
  results: AgentTestExtractResult[];
  progress?: AgentTestProgress;
}

// Preview / Preview-then-push Types
export interface AgentPreviewListing {
  raw_message_id: string;
  raw_text: string;
  title: string;
  district: string | null;
  bedrooms: number | null;
  price_vnd: number | null;
  area_m2: number | null;
  image_count: number;
  payload: Record<string, unknown>;
  operation: "insert" | "update" | "skip";
  existing_villa_id: string | null;
  source_message_ids: string[];
}

export interface AgentPreviewResponse {
  total_messages_seen: number;
  classified_listing: number;
  extracted_ok: number;
  would_insert: number;
  would_update: number;
  would_skip: number;
  listings: AgentPreviewListing[];
}
