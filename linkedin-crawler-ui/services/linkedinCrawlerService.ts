import { API_BASE_URL, API_KEY } from "@/lib/env";
import type {
  AddListGroupRequest,
  AddN8nGroupRequest,
  BulkGroupImportResponse,
  EnsureProfileSlugResponse,
  CrawlGroupRequest,
  CrawlResponse,
  FilterDataRequest,
  FilterDataResponse,
  GetAllN8nGroupsRequest,
  GetAllPostsRequest,
  GetAllPostsResponse,
  LoginRequest,
  LoginResponse,
  PostLinkedInCommentRequest,
  PostLinkedInCommentResponse,
  PostLinkedInReactionRequest,
  PostLinkedInReactionResponse,
  N8nGroupOperationResponse,
  RemoveN8nGroupRequest,
  StartWorkflowRequest,
  StartWorkflowResponse,
  StatusResponse,
  UpdateN8nGroupRequest,
  VerifyLoginRequest,
  VerifyLoginResponse,
  ProfileSlugSheetCheckResponse,
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
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: init?.credentials ?? "include",
    headers: {
      ...buildHeaders(),
      ...init?.headers,
    },
  });

  const payload = (await response.json()) as TResponse;
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
  return requestJson<StatusResponse>("/status", { method: "GET" });
}

export function loginLinkedIn(payload: LoginRequest): Promise<LoginResponse> {
  return requestJson<LoginResponse>("/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function checkProfileSlugInSheet(payload: {
  email: string;
}): Promise<ProfileSlugSheetCheckResponse> {
  return requestJson<ProfileSlugSheetCheckResponse>(
    "/linkedin/me/profile-slug-sheet-check",
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
  return requestJson<EnsureProfileSlugResponse>("/linkedin/me/ensure-profile-slug", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function verifyLinkedInOtp(
  payload: VerifyLoginRequest,
): Promise<VerifyLoginResponse> {
  return requestJson<VerifyLoginResponse>("/verify", {
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
  return requestJson<StartWorkflowResponse>("/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function crawlLinkedInGroup(
  payload: CrawlGroupRequest,
): Promise<CrawlResponse> {
  return requestJson<CrawlResponse>("/crawl-linkedin-group", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function filterLinkedInPosts(
  payload: FilterDataRequest,
): Promise<FilterDataResponse> {
  return requestJson<FilterDataResponse>("/filter-data", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAllLinkedInPosts(
  payload: GetAllPostsRequest,
): Promise<GetAllPostsResponse> {
  return requestJson<GetAllPostsResponse>("/get-all-posts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Playwright reaction trên URL bài + webhook ``N8N_WEBHOOK_POST_REACTION`` (ghi sheet). */
export function postLinkedInReaction(
  payload: PostLinkedInReactionRequest,
): Promise<PostLinkedInReactionResponse> {
  const body: Record<string, unknown> = {
    post_url: payload.post_url.trim(),
    reaction: payload.reaction,
    Email_crawl: payload.Email_crawl.trim(),
    ID_session_crawl: payload.ID_session_crawl.trim(),
    row_number: payload.row_number,
    post_to_webhook: payload.post_to_webhook ?? true,
  };
  if (payload.sheet_row && typeof payload.sheet_row === "object") {
    body.sheet_row = payload.sheet_row;
  }
  const sid = payload.session_id?.trim();
  if (sid) body.session_id = sid;
  if (payload.email?.trim()) body.email = payload.email.trim();
  return requestJson<PostLinkedInReactionResponse>("/linkedin/post/react", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Playwright đăng comment + webhook ``N8N_WEBHOOK_COMMENT`` / ``N8N_WEBHOOK_POST_COMMENT``. */
export function postLinkedInComment(
  payload: PostLinkedInCommentRequest,
): Promise<PostLinkedInCommentResponse> {
  const body: Record<string, unknown> = {
    post_url: payload.post_url.trim(),
    comment_text: payload.comment_text.trim(),
    Email_crawl: payload.Email_crawl.trim(),
    ID_session_crawl: payload.ID_session_crawl.trim(),
    row_number: payload.row_number,
    existing_app_comments: payload.existing_app_comments.map((e) => ({
      comment: e.comment.trim(),
      day_comment: e.day_comment.trim(),
    })),
    post_to_webhook: payload.post_to_webhook ?? true,
    typing_delay_ms: payload.typing_delay_ms ?? 30,
    timeout_ms: payload.timeout_ms ?? 20000,
  };
  if (payload.sheet_row && typeof payload.sheet_row === "object") {
    body.sheet_row = payload.sheet_row;
  }
  const sid = payload.session_id?.trim();
  if (sid) body.session_id = sid;
  if (payload.email?.trim()) body.email = payload.email.trim();
  return requestJson<PostLinkedInCommentResponse>("/linkedin/post/comment", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getAllN8nGroups(
  payload: GetAllN8nGroupsRequest,
): Promise<N8nGroupOperationResponse> {
  return requestJson<N8nGroupOperationResponse>("/groups/n8n-get-all", {
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
  return requestJson<BulkGroupImportResponse>("/groups/add-list-group", {
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
  return requestJson<N8nGroupOperationResponse>("/groups/add", {
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
  return requestJson<N8nGroupOperationResponse>("/groups/remove", {
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
  return requestJson<N8nGroupOperationResponse>("/groups/update", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
