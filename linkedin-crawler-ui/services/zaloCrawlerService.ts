import { API_BASE_URL, API_KEY } from "@/lib/env";
import type {
  ZaloAuthInitResponse,
  ZaloAccountsResponse,
  ZaloAuthStatusResponse,
  ZaloCurrentStatusResponse,
  ZaloCrawledGroupsResponse,
  ZaloDeleteSessionResponse,
  ZaloBroadcastPreviewResponse,
  ZaloBroadcastRequest,
  ZaloBroadcastResponse,
  ZaloBroadcastStatusResponse,
  ZaloJobData,
  ZaloConversationListResponse,
  ZaloLibraryContentKind,
  ZaloInboxReportResponse,
  ZaloLibraryListResponse,
  ZaloLibraryMessage,
  ZaloLibraryBulkDeleteRequest,
  ZaloLibraryBulkDeleteResponse,
  ZaloLibraryMessageCreateRequest,
  ZaloLibraryMessageUpdateRequest,
  ZaloLiveGroup,
  ZaloManualLoginResponse,
  ZaloStartCrawlRequest,
  ZaloStartCrawlResponse,
  ZaloSyncRecentResponse,
  ZaloVerifyGroupRequestItem,
  ZaloVerifyGroupsResponse,
  ZaloWorkersResponse,
} from "@/types/zalo-api";

const JSON_HEADERS = {
  "Content-Type": "application/json",
} as const;

export const ZALO_WORKER_STORAGE_KEY = "zalo_selected_worker_id";

export function normalizeZaloWorkerId(value?: string | null): string {
  return (value ?? "")
    .trim()
    .toLowerCase()
    .replaceAll("_", "-")
    .replace(/[^a-z0-9.-]/g, "");
}

export function getDefaultZaloWorkerId(): string {
  return "default";
}

export function getSelectedZaloWorkerId(): string {
  if (typeof window === "undefined") return getDefaultZaloWorkerId();
  const stored = normalizeZaloWorkerId(window.localStorage.getItem(ZALO_WORKER_STORAGE_KEY));
  if (stored) return stored;
  const fallback = getDefaultZaloWorkerId();
  window.localStorage.setItem(ZALO_WORKER_STORAGE_KEY, fallback);
  return fallback;
}

export function setSelectedZaloWorkerId(workerId: string): string {
  const normalized = normalizeZaloWorkerId(workerId) || getDefaultZaloWorkerId();
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ZALO_WORKER_STORAGE_KEY, normalized);
  }
  return normalized;
}

export function getZaloWorkers(userId = "default"): Promise<ZaloWorkersResponse> {
  return requestJson<ZaloWorkersResponse>("/api/zalo/workers", {
    method: "GET",
    headers: {
      "X-User-ID": userId,
    },
  }, 7000);
}

export function getZaloAccounts(ownerId = "default"): Promise<ZaloAccountsResponse> {
  const params = new URLSearchParams({ owner_id: ownerId });
  return requestJson<ZaloAccountsResponse>(`/api/zalo/accounts?${params.toString()}`, {
    method: "GET",
    headers: {
      "X-User-ID": ownerId,
    },
  });
}

export function createZaloAccount(payload: {
  account_id?: string;
  owner_id?: string;
  label: string;
  phone?: string;
}) {
  return requestJson("/api/zalo/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateZaloAccount(
  accountId: string,
  payload: {
    owner_id?: string;
    label?: string;
    phone?: string;
    status?: string;
  }
) {
  return requestJson(`/api/zalo/accounts/${encodeURIComponent(accountId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteZaloAccount(accountId: string, deleteAuth = false) {
  const params = new URLSearchParams({ delete_auth: String(deleteAuth) });
  return requestJson(`/api/zalo/accounts/${encodeURIComponent(accountId)}?${params.toString()}`, {
    method: "DELETE",
  });
}

export function restartZaloAccountListener(accountId: string) {
  return requestJson(`/api/zalo/accounts/${encodeURIComponent(accountId)}/listener/restart`, {
    method: "POST",
  });
}

export function getZaloInboxReport(ownerId = "default", accountIds: string[] = []): Promise<ZaloInboxReportResponse> {
  const params = new URLSearchParams({ owner_id: ownerId });
  for (const accountId of accountIds) params.append("account_id", accountId);
  return requestJson<ZaloInboxReportResponse>(`/api/zalo/accounts/inbox-report?${params.toString()}`, {
    method: "GET",
    headers: {
      "X-User-ID": ownerId,
    },
  });
}

export function getZaloConversations(accountId = "default"): Promise<ZaloConversationListResponse> {
  const params = new URLSearchParams({ account_id: accountId });
  return requestJson<ZaloConversationListResponse>(`/api/zalo/conversations?${params.toString()}`, {
    method: "GET",
    headers: {
      "X-User-ID": accountId,
    },
  });
}

export function getZaloConversationMessages(
  accountId: string,
  conversationId: string,
  limit = 100,
  offset = 0,
): Promise<ZaloLibraryListResponse> {
  const params = new URLSearchParams({
    account_id: accountId,
    limit: String(limit),
    offset: String(offset),
  });
  return requestJson<ZaloLibraryListResponse>(
    `/api/zalo/conversations/${encodeURIComponent(conversationId)}/messages?${params.toString()}`,
    {
      method: "GET",
      headers: {
        "X-User-ID": accountId,
      },
    },
  );
}

export function syncZaloRecentConversations(
  accountId: string,
  limit = 50,
  messagesPerConversation = 50,
): Promise<ZaloSyncRecentResponse> {
  return requestJson<ZaloSyncRecentResponse>("/api/zalo/conversations/sync-recent", {
    method: "POST",
    headers: {
      "X-User-ID": accountId,
    },
    body: JSON.stringify({
      account_id: accountId,
      limit,
      messages_per_conversation: messagesPerConversation,
    }),
  });
}

function buildHeaders(extra?: HeadersInit, isFormData = false): HeadersInit {
  const baseHeaders: HeadersInit = API_KEY
    ? {
        ...(isFormData ? {} : JSON_HEADERS),
        "x-api-key": API_KEY,
      }
    : {
        ...(isFormData ? {} : JSON_HEADERS),
      };

  return {
    ...baseHeaders,
    ...extra,
  };
}

async function requestJson<TResponse>(
  path: string,
  init?: RequestInit,
  timeoutMs?: number,
): Promise<TResponse> {
  const timeoutController = timeoutMs ? new AbortController() : null;
  const timeoutId = timeoutController
    ? globalThis.setTimeout(() => timeoutController.abort(), timeoutMs)
    : null;

  const isFormData = init?.body instanceof FormData;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: init?.credentials ?? "include",
      headers: buildHeaders(init?.headers, isFormData),
      signal: init?.signal ?? timeoutController?.signal,
    });
  } catch (error) {
    if (timeoutController?.signal.aborted) {
      throw new Error(`Request timed out after ${Math.round((timeoutMs ?? 0) / 1000)}s`);
    }
    throw error;
  } finally {
    if (timeoutId) globalThis.clearTimeout(timeoutId);
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
      | { message?: unknown; detail?: unknown; error?: { kind?: string; message?: string; missing?: string[]; request_id?: string } }
      | undefined;

    // Check for typed ApartmentAgentError envelope
    const agentError = errorPayload?.error;
    if (agentError?.kind) {
      let msg = agentError.message || "";
      if (agentError.kind === "missing_config" && agentError.missing?.length) {
        msg = `Thiếu ${agentError.missing.join(", ")} trong .env — xem .env.example`;
      }
      if (agentError.request_id) {
        msg += ` [request_id: ${agentError.request_id}]`;
      }
      throw new Error(`API ${response.status}: ${msg}`);
    }

    const normalizeErrorValue = (value: unknown): string => {
      if (typeof value === "string") return value.trim();
      if (!value) return "";
      if (typeof value === "object") {
        const objectValue = value as { message?: unknown; detail?: unknown };
        const nestedMessage = normalizeErrorValue(objectValue.message);
        if (nestedMessage) return nestedMessage;
        const nestedDetail = normalizeErrorValue(objectValue.detail);
        if (nestedDetail) return nestedDetail;
        try {
          return JSON.stringify(value);
        } catch {
          return String(value);
        }
      }
      return String(value).trim();
    };
    const backendMessage =
      normalizeErrorValue(errorPayload?.message) || normalizeErrorValue(errorPayload?.detail);

    throw new Error(
      backendMessage
        ? `API ${response.status}: ${backendMessage}`
        : `API ${response.status}: ${response.statusText}`,
    );
  }

  return payload;
}

export function initZaloAuthSession(
  userId = "default",
): Promise<ZaloAuthInitResponse> {
  return requestJson<ZaloAuthInitResponse>("/api/zalo/auth/init", {
    method: "POST",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
  }, 95000);
}

export function refreshZaloLoginQr(
  userId = "default",
): Promise<ZaloAuthInitResponse> {
  return requestJson<ZaloAuthInitResponse>("/api/zalo/auth/qr/refresh", {
    method: "POST",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
  }, 95000);
}

export function getZaloAuthStatus(
  sessionId: string,
): Promise<ZaloAuthStatusResponse> {
  return requestJson<ZaloAuthStatusResponse>(
    `/api/zalo/auth/status/${encodeURIComponent(sessionId)}`,
    {
      method: "GET",
    },
  );
}

export function getZaloCurrentStatus(
  userId = "default",
): Promise<ZaloCurrentStatusResponse> {
  return requestJson<ZaloCurrentStatusResponse>(
    "/api/zalo/auth/current-status",
    {
      method: "GET",
      headers: buildHeaders({
        "X-User-ID": userId,
      }),
    },
  );
}

export function startZaloManualLogin(
  userId = "default",
): Promise<ZaloManualLoginResponse> {
  return requestJson<ZaloManualLoginResponse>("/api/zalo/auth/manual-login/start", {
    method: "POST",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
  });
}

export function resumeZaloManualLogin(
  userId = "default",
): Promise<ZaloManualLoginResponse> {
  return requestJson<ZaloManualLoginResponse>("/api/zalo/auth/manual-login/resume", {
    method: "POST",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
  });
}

export function deleteZaloSession(
  sessionId: string,
): Promise<ZaloDeleteSessionResponse> {
  return requestJson<ZaloDeleteSessionResponse>(
    `/api/zalo/auth/session/${encodeURIComponent(sessionId)}`,
    {
      method: "DELETE",
    },
  );
}

export function deleteAllZaloSessions(
  userId = "default",
): Promise<ZaloDeleteSessionResponse> {
  return requestJson<ZaloDeleteSessionResponse>("/api/zalo/auth/sessions", {
    method: "DELETE",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
  });
}

export function startZaloCrawl(
  payload: ZaloStartCrawlRequest,
): Promise<ZaloStartCrawlResponse> {
  const headers: HeadersInit = {
    "X-User-ID": payload.userId?.trim() || "default",
  };
  if (payload.sessionId?.trim()) {
    headers["X-Session-ID"] = payload.sessionId.trim();
  }

  return requestJson<ZaloStartCrawlResponse>("/api/zalo/crawl", {
    method: "POST",
    headers: buildHeaders(headers),
    body: JSON.stringify({
      group_name: payload.group_name.trim(),
      group_id: payload.group_id?.trim() || undefined,
      sheet_tab: payload.sheet_tab?.trim() || undefined,
      max_messages: Math.max(1, Math.min(payload.max_messages ?? 50, 500)),
    }),
  });
}

export function getZaloJob(jobId: string, userId = "default"): Promise<ZaloJobData> {
  return requestJson<ZaloJobData>(
    `/api/zalo/jobs/${encodeURIComponent(jobId)}`,
    {
      method: "GET",
      headers: buildHeaders({
        "X-User-ID": userId,
      }),
    },
  );
}

export function getZaloJobs(userId = "default"): Promise<ZaloJobData[]> {
  return requestJson<ZaloJobData[]>("/api/zalo/jobs", {
    method: "GET",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
  });
}

export function buildZaloJobEventsUrl(userId = "default"): string {
  const params = new URLSearchParams({ user_id: userId });
  if (API_KEY) params.set("api_key", API_KEY);
  return `${API_BASE_URL}/api/zalo/jobs/events?${params.toString()}`;
}

export function getZaloCrawledGroups(userId = "default"): Promise<ZaloCrawledGroupsResponse> {
  return requestJson<ZaloCrawledGroupsResponse>("/api/zalo/groups/crawled", {
    method: "GET",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
  });
}

export function getZaloLiveGroups(userId = "default"): Promise<ZaloLiveGroup[]> {
  return requestJson<ZaloLiveGroup[]>("/api/groups", {
    method: "GET",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
  });
}

export function verifyZaloGroups(
  userId = "default",
  groups: ZaloVerifyGroupRequestItem[],
  sessionId?: string | null,
): Promise<ZaloVerifyGroupsResponse> {
  const headers: HeadersInit = {
    "X-User-ID": userId,
  };
  if (sessionId?.trim()) {
    headers["X-Session-ID"] = sessionId.trim();
  }

  return requestJson<ZaloVerifyGroupsResponse>("/api/zalo/groups/verify", {
    method: "POST",
    headers: buildHeaders(headers),
    body: JSON.stringify({ groups }),
  });
}

export function getZaloLibraryMessages(
  userId = "default",
  groupName?: string,
  limit = 50,
  offset = 0,
  contentKind: ZaloLibraryContentKind = "all",
): Promise<ZaloLibraryListResponse> {
  const params = new URLSearchParams();
  if (groupName?.trim()) params.set("group_name", groupName.trim());
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  params.set("content_kind", contentKind);
  const query = params.toString();
  return requestJson<ZaloLibraryListResponse>(
    `/api/zalo/library/messages${query ? `?${query}` : ""}`,
    {
      method: "GET",
      headers: buildHeaders({
        "X-User-ID": userId,
      }),
    },
  );
}

export function createZaloLibraryMessage(
  userId: string,
  payload: ZaloLibraryMessageCreateRequest,
): Promise<ZaloLibraryMessage> {
  return requestJson<ZaloLibraryMessage>("/api/zalo/library/messages", {
    method: "POST",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
    body: JSON.stringify(payload),
  });
}

export function updateZaloLibraryMessage(
  userId: string,
  messageId: string,
  payload: ZaloLibraryMessageUpdateRequest,
): Promise<ZaloLibraryMessage> {
  return requestJson<ZaloLibraryMessage>(
    `/api/zalo/library/messages/${encodeURIComponent(messageId)}`,
    {
      method: "PATCH",
      headers: buildHeaders({
        "X-User-ID": userId,
      }),
      body: JSON.stringify(payload),
    },
  );
}

export function deleteZaloLibraryMessage(
  userId: string,
  messageId: string,
): Promise<ZaloLibraryMessage> {
  return requestJson<ZaloLibraryMessage>(
    `/api/zalo/library/messages/${encodeURIComponent(messageId)}`,
    {
      method: "DELETE",
      headers: buildHeaders({
        "X-User-ID": userId,
      }),
    },
  );
}

export function bulkDeleteZaloLibraryMessages(
  userId: string,
  payload: ZaloLibraryBulkDeleteRequest,
): Promise<ZaloLibraryBulkDeleteResponse> {
  return requestJson<ZaloLibraryBulkDeleteResponse>("/api/zalo/library/messages/bulk-delete", {
    method: "POST",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
    body: JSON.stringify(payload),
  });
}

export function previewZaloBroadcast(
  userId: string,
  payload: ZaloBroadcastRequest,
): Promise<ZaloBroadcastPreviewResponse> {
  return requestJson<ZaloBroadcastPreviewResponse>("/api/zalo/broadcasts/preview", {
    method: "POST",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
    body: JSON.stringify(payload),
  });
}

export function createZaloBroadcast(
  userId: string,
  payload: ZaloBroadcastRequest,
): Promise<ZaloBroadcastResponse> {
  return requestJson<ZaloBroadcastResponse>("/api/zalo/broadcasts", {
    method: "POST",
    headers: buildHeaders({
      "X-User-ID": userId,
    }),
    body: JSON.stringify(payload),
  });
}

export function getZaloBroadcast(
  campaignId: string,
): Promise<ZaloBroadcastStatusResponse> {
  return requestJson<ZaloBroadcastStatusResponse>(
    `/api/zalo/broadcasts/${encodeURIComponent(campaignId)}`,
    {
      method: "GET",
    },
  );
}

export function testAgentExtract(
  request: { group_name?: string; texts?: string[] },
): Promise<import("@/types/zalo-api").AgentTestExtractResponse> {
  return requestJson<import("@/types/zalo-api").AgentTestExtractResponse>(
    "/api/apartment-agent/test-extract",
    { method: "POST", body: JSON.stringify(request) },
    120000,
  );
}

export function previewAgentExtract(
  request: { group_name?: string; texts?: string[] },
): Promise<import("@/types/zalo-api").AgentPreviewResponse> {
  return requestJson<import("@/types/zalo-api").AgentPreviewResponse>(
    "/api/apartment-agent/preview",
    { method: "POST", body: JSON.stringify(request) },
    300000,
  );
}

export interface VillaSyncResponse {
  total_messages_processed: number;
  apartments_found: number;
  new_villas_created: number;
  villas_updated: number;
  villas_marked_rented: number;
  errors: string[];
  dry_run: boolean;
}

export function villaSync(
  request: { user_id?: string; dry_run?: boolean; listing_ids?: string[] } = {},
): Promise<VillaSyncResponse> {
  return requestJson<VillaSyncResponse>(
    "/api/zalo/villa-sync",
    {
      method: "POST",
      body: JSON.stringify({
        user_id: request.user_id || "default",
        dry_run: request.dry_run ?? false,
        listing_ids: request.listing_ids,
      }),
    },
    600000,
  );
}

export interface ZaloSendMessageRequest {
  text: string;
  thread_type?: number;
}

export interface ZaloSendMessageResponse {
  ok: boolean;
  conversation_id: string;
  message: string;
}

export function sendZaloMessage(
  accountId: string,
  conversationId: string,
  payload: ZaloSendMessageRequest,
): Promise<ZaloSendMessageResponse> {
  return requestJson<ZaloSendMessageResponse>(
    `/api/zalo/conversations/${encodeURIComponent(conversationId)}/send`,
    {
      method: "POST",
      headers: buildHeaders({
        "X-User-ID": accountId,
      }),
      body: JSON.stringify(payload),
    },
  );
}

export function sendZaloMessageWithFiles(
  accountId: string,
  conversationId: string,
  text: string,
  files: File[],
  threadType?: number,
): Promise<ZaloSendMessageResponse> {
  const formData = new FormData();
  if (text) {
    formData.append("text", text);
  }
  if (threadType !== undefined) {
    formData.append("thread_type", String(threadType));
  }
  for (const file of files) {
    formData.append("files", file);
  }

  return requestJson<ZaloSendMessageResponse>(
    `/api/zalo/conversations/${encodeURIComponent(conversationId)}/send-media`,
    {
      method: "POST",
      headers: {
        "X-User-ID": accountId,
      },
      body: formData,
    },
    180000, // 3 minutes timeout for media uploads
  );
}

export interface ZaloMarkReadResponse {
  ok: boolean;
  conversation_id: string;
  message: string;
}

export function markZaloConversationAsRead(
  accountId: string,
  conversationId: string,
): Promise<ZaloMarkReadResponse> {
  return requestJson<ZaloMarkReadResponse>(
    `/api/zalo/conversations/${encodeURIComponent(conversationId)}/read`,
    {
      method: "POST",
      headers: buildHeaders({
        "X-User-ID": accountId,
      }),
    },
  );
}
