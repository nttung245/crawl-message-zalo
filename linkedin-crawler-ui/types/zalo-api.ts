export type ZaloAuthStatus = "waiting_scan" | "confirmed" | "qr_expired";

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

export interface ZaloRefreshQrResponse {
  qr_base64: string;
  status: "waiting_scan";
}

export interface ZaloDeleteSessionResponse {
  message: string;
}

export interface ZaloStartCrawlRequest {
  sessionId: string;
  group_name: string;
  sheet_tab?: string;
}

export interface ZaloStartCrawlResponse {
  job_id: string;
  status: "queued" | "running";
  sheet_url: string;
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
