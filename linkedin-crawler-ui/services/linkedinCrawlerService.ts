import { API_BASE_URL, API_KEY } from "@/lib/env";
import type {
  AddListGroupRequest,
  AddMemberRequest,
  AddMemberResponse,
  AddN8nGroupRequest,
  ApiResponse,
  AssignKpiRequest,
  BulkGroupImportResponse,
  CheckPermissionRequest,
  CheckPermissionResponse,
  EnsureProfileSlugResponse,
  CrawlGroupRequest,
  CrawlResponse,
  FilterDataRequest,
  FilterDataResponse,
  GetAllKpiRequest,
  GetAllKpiResponse,
  GetAllN8nGroupsRequest,
  GetAllPostsRequest,
  GetAllPostsResponse,
  GetKpiByEmailRequest,
  GetKpiByEmailResponse,
  LoginRequest,
  LoginResponse,
  N8nGroupOperationResponse,
  RemoveN8nGroupRequest,
  StartWorkflowRequest,
  StartWorkflowResponse,
  StatusResponse,
  UpdateN8nGroupRequest,
  VerifyLeaderCodeRequest,
  VerifyLoginRequest,
  VerifyLoginResponse,
  ProfileSlugSheetCheckResponse,
  GetMyProfileSlugResponse,
  LinkedinAppStatsRequest,
  LinkedinAppStatsResponse,
  GetProfilesRequest,
  UpdateProfileSlugRequest,
} from "@/types/api";

const JSON_HEADERS = {
  "Content-Type": "application/json",
} as const;

function buildHeaders(): HeadersInit {
  if (!API_KEY) {
    return JSON_HEADERS;
  }
  return {
    ...JSON_HEADERS,
    "x-api-key": API_KEY,
  };
}

async function requestJson<TResponse>(
  path: string,
  init?: RequestInit,
): Promise<TResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: init?.credentials ?? "include",
      headers: {
        ...buildHeaders(),
        ...init?.headers,
      },
    });
  } catch (error) {
    const hint =
      error instanceof Error ? error.message : String(error);
    throw new Error(
      `Không kết nối được API (${API_BASE_URL}${path}): ${hint}`,
    );
  }

  let payload: TResponse;
  try {
    payload = (await response.json()) as TResponse;
  } catch {
    throw new Error(
      `API ${response.status}: phản hồi không phải JSON (${API_BASE_URL}${path})`,
    );
  }
  if (!response.ok) {
    const errorPayload = payload as
      | { message?: string; detail?: string }
      | undefined;
    const backendMessage =
      errorPayload?.message?.trim() || errorPayload?.detail?.trim();
    throw new Error(
      backendMessage
        ? `API ${response.status}: ${backendMessage}`
        : `API ${response.status}: ${response.statusText}`,
    );
  }
  return payload;
}

export function fetchCrawlerStatus(): Promise<StatusResponse> {
  return requestJson<StatusResponse>("/api/linkedin/status", { method: "GET" });
}

export function loginLinkedIn(payload: LoginRequest): Promise<LoginResponse> {
  return requestJson<LoginResponse>("/api/linkedin/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function checkProfileSlugInSheet(payload: {
  email: string;
}): Promise<ProfileSlugSheetCheckResponse> {
  return requestJson<ProfileSlugSheetCheckResponse>(
    "/api/linkedin/me/profile-slug-sheet-check",
    {
      method: "POST",
      body: JSON.stringify({ email: payload.email.trim() }),
    },
  );
}

/** Sau login / verify: kiểm tra sheet → nếu chưa có email thì cào slug + webhook add. */
export function ensureProfileSlugIfMissing(payload: {
  email: string;
  sessionId?: string | null;
}): Promise<EnsureProfileSlugResponse> {
  const body: Record<string, unknown> = { email: payload.email.trim() };
  const sid = payload.sessionId?.trim();
  if (sid) body.session_id = sid;
  return requestJson<EnsureProfileSlugResponse>(
    "/api/linkedin/me/ensure-profile-slug",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

/** Lấy profile slug qua Playwright (menu Me → View profile). Cần ít nhất một trong sessionId, email. */
export function getMyProfileSlug(payload: {
  sessionId?: string | null;
  email?: string | null;
}): Promise<GetMyProfileSlugResponse> {
  const session_id = payload.sessionId?.trim() || undefined;
  const email = payload.email?.trim() || undefined;
  const body: Record<string, unknown> = {};
  if (session_id) body.session_id = session_id;
  if (email) body.email = email;
  return requestJson<GetMyProfileSlugResponse>("/api/linkedin/me/profile-slug", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function verifyLinkedInOtp(
  payload: VerifyLoginRequest,
): Promise<VerifyLoginResponse> {
  return requestJson<VerifyLoginResponse>("/api/linkedin/verify", {
    method: "POST",
    body: JSON.stringify({
      session_id: payload.sessionId,
      otp: payload.otp,
      checkpoint_url: payload.checkpointUrl,
    }),
  });
}

export function startN8nWorkflow(
  payload: StartWorkflowRequest,
): Promise<StartWorkflowResponse> {
  return requestJson<StartWorkflowResponse>("/api/linkedin/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function crawlLinkedInGroup(
  payload: CrawlGroupRequest,
): Promise<CrawlResponse> {
  return requestJson<CrawlResponse>("/api/linkedin/crawl-linkedin-group", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function filterLinkedInPosts(
  payload: FilterDataRequest,
): Promise<FilterDataResponse> {
  return requestJson<FilterDataResponse>("/api/linkedin/filter-data", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAllLinkedInPosts(
  payload: GetAllPostsRequest,
): Promise<GetAllPostsResponse> {
  return requestJson<GetAllPostsResponse>("/api/linkedin/get-all-posts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAllN8nGroups(
  payload: GetAllN8nGroupsRequest,
): Promise<N8nGroupOperationResponse> {
  return requestJson<N8nGroupOperationResponse>("/api/linkedin/groups/n8n-get-all", {
    method: "POST",
    body: JSON.stringify({ email: payload.email.trim() }),
  });
}

export function addListGroupBulk(
  payload: AddListGroupRequest,
): Promise<BulkGroupImportResponse> {
  const body: Record<string, unknown> = {
    group_urls: payload.group_urls.map((u) => u.trim()).filter(Boolean),
    post_to_webhook: payload.post_to_webhook ?? true,
    delay_min_sec: payload.delay_min_sec ?? 2,
    delay_max_sec: payload.delay_max_sec ?? 5,
  };
  if (payload.email?.trim()) body.email = payload.email.trim();
  if (payload.webhook_timeout_sec != null)
    body.webhook_timeout_sec = payload.webhook_timeout_sec;
  return requestJson<BulkGroupImportResponse>("/api/linkedin/groups/add-list-group", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function addN8nGroup(
  payload: AddN8nGroupRequest,
): Promise<N8nGroupOperationResponse> {
  const body: Record<string, unknown> = {
    url_group: payload.url_group.trim(),
    name_group: payload.name_group.trim(),
    member: payload.member,
  };
  if (payload.email?.trim()) body.email = payload.email.trim();
  return requestJson<N8nGroupOperationResponse>("/api/linkedin/groups/add", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function removeN8nGroup(
  payload: RemoveN8nGroupRequest,
): Promise<N8nGroupOperationResponse> {
  const body: Record<string, unknown> = {
    url_group: payload.url_group.trim(),
  };
  if (payload.email?.trim()) body.email = payload.email.trim();
  return requestJson<N8nGroupOperationResponse>("/api/linkedin/groups/remove", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateN8nGroup(
  payload: UpdateN8nGroupRequest,
): Promise<N8nGroupOperationResponse> {
  const body: Record<string, unknown> = {
    url_group_need_update: payload.url_group_need_update.trim(),
    name_group: payload.name_group.trim(),
    member: payload.member,
  };
  if (payload.new_url_group != null && payload.new_url_group !== "")
    body.new_url_group = payload.new_url_group.trim();
  if (payload.new_name_group != null && payload.new_name_group !== "")
    body.new_name_group = payload.new_name_group.trim();
  if (payload.new_member != null) body.new_member = payload.new_member;
  if (payload.email?.trim()) body.email = payload.email.trim();
  return requestJson<N8nGroupOperationResponse>("/api/linkedin/groups/update", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Đọc lại tiến độ (reaction/comments) cho 1 bài viết. */
export function syncPostProgress(payload: {
  post_url: string;
  profile_slug: string;
  Email_crawl: string;
  ID_session_crawl: string;
  row_number: number;
  sheet_row?: Record<string, unknown> | null;
  session_id?: string | null;
  email?: string | null;
  password?: string | null;
  auto_login?: boolean;
  post_to_webhook?: boolean;
  timeout_ms?: number;
}): Promise<import("@/types/api").SyncPostProgressResponse> {
  return requestJson<import("@/types/api").SyncPostProgressResponse>(
    "/api/linkedin/post/sync-progress",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

/** Đọc lại tiến độ cho toàn bộ bài viết của user. */
export function syncAllProgress(payload: {
  email_crawl: string;
  profile_slug: string;
  session_id?: string | null;
  email?: string | null;
  password?: string | null;
  auto_login?: boolean;
  timeout_ms_per_post?: number;
  limit_posts?: number;
}): Promise<import("@/types/api").SyncAllProgressResponse> {
  return requestJson<import("@/types/api").SyncAllProgressResponse>(
    "/api/linkedin/sync-all-progress",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getLinkedInStats(
  payload: LinkedinAppStatsRequest,
): Promise<LinkedinAppStatsResponse> {
  return requestJson<LinkedinAppStatsResponse>("/api/linkedin/app/stats", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Leader gán KPI cho member. */
export function assignKpi(
  payload: AssignKpiRequest,
): Promise<ApiResponse<unknown>> {
  return requestJson<ApiResponse<unknown>>("/api/linkedin/kpi/assign", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Kiểm tra quyền leader/member. */
export function checkPermission(
  payload: CheckPermissionRequest,
): Promise<CheckPermissionResponse> {
  return requestJson<CheckPermissionResponse>("/api/linkedin/auth/check-permission", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Lấy toàn bộ KPI cho leader. */
export function getAllKpi(
  payload: GetAllKpiRequest,
): Promise<GetAllKpiResponse> {
  return requestJson<GetAllKpiResponse>("/api/linkedin/kpi/get-all", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Lấy KPI cho member theo email. */
export function getKpiByEmail(
  payload: GetKpiByEmailRequest,
): Promise<GetKpiByEmailResponse> {
  return requestJson<GetKpiByEmailResponse>("/api/linkedin/kpi/get-by-email", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Thêm thành viên mới vào đội ngũ. */
export function addMember(
  payload: AddMemberRequest,
): Promise<AddMemberResponse> {
  return requestJson<AddMemberResponse>("/api/linkedin/team/add-member", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Xác nhận mã code leader. */
export function verifyLeaderCode(
  payload: VerifyLeaderCodeRequest,
): Promise<ApiResponse<unknown>> {
  return requestJson<ApiResponse<unknown>>("/api/linkedin/auth/verify-leader-code", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
export const getAllProfiles = async (
  payload: GetProfilesRequest,
): Promise<ApiResponse<any[]>> => {
  const response = await fetch(`${API_BASE_URL}/api/linkedin/all-profiles`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": API_KEY,
    },
    body: JSON.stringify(payload),
  });
  return response.json();
};
export function updateProfileSlug(
  payload: UpdateProfileSlugRequest,
): Promise<ApiResponse<unknown>> {
  return requestJson<ApiResponse<unknown>>("/api/linkedin/me/profile-slug-update", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
