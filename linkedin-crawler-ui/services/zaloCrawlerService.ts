import { API_BASE_URL, API_KEY } from "@/lib/env";
import type {
  ZaloAuthInitResponse,
  ZaloAuthStatusResponse,
  ZaloCurrentStatusResponse,
  ZaloCrawledGroupsResponse,
  ZaloDeleteSessionResponse,
  ZaloBroadcastPreviewResponse,
  ZaloBroadcastRequest,
  ZaloBroadcastResponse,
  ZaloBroadcastStatusResponse,
  ZaloJobData,
  ZaloLibraryContentKind,
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

function buildHeaders(extra?: HeadersInit): HeadersInit {
  const baseHeaders: HeadersInit = API_KEY
    ? {
        ...JSON_HEADERS,
        "x-api-key": API_KEY,
      }
    : {
        ...JSON_HEADERS,
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

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: init?.credentials ?? "include",
      headers: buildHeaders(init?.headers),
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

  const payload = (await response.json()) as TResponse;

  if (!response.ok) {
    const errorPayload = payload as
      | { message?: unknown; detail?: unknown }
      | undefined;
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
    {
      method: "POST",
      body: JSON.stringify(request),
    },
    120000,
  );
}
