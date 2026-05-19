import { API_BASE_URL, API_KEY } from "@/lib/env";
import type {
  ZaloAuthInitResponse,
  ZaloAuthStatusResponse,
  ZaloDeleteSessionResponse,
  ZaloJobData,
  ZaloRefreshQrResponse,
  ZaloStartCrawlRequest,
  ZaloStartCrawlResponse,
} from "@/types/zalo-api";

const JSON_HEADERS = {
  "Content-Type": "application/json",
} as const;

function buildHeaders(extra?: HeadersInit): HeadersInit {
  const baseHeaders: HeadersInit = API_KEY
    ? {
        ...JSON_HEADERS,
        "x-api-key": API_KEY,
      }
    : JSON_HEADERS;

  return {
    ...baseHeaders,
    ...extra,
  };
}

async function requestJson<TResponse>(
  path: string,
  init?: RequestInit,
): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: init?.credentials ?? "include",
    headers: buildHeaders(init?.headers),
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

export function initZaloAuthSession(): Promise<ZaloAuthInitResponse> {
  return requestJson<ZaloAuthInitResponse>("/api/zalo/auth/init", {
    method: "POST",
  });
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

export function refreshZaloQr(
  sessionId: string,
): Promise<ZaloRefreshQrResponse> {
  return requestJson<ZaloRefreshQrResponse>(
    `/api/zalo/auth/refresh-qr/${encodeURIComponent(sessionId)}`,
    {
      method: "POST",
    },
  );
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

export function startZaloCrawl(
  payload: ZaloStartCrawlRequest,
): Promise<ZaloStartCrawlResponse> {
  return requestJson<ZaloStartCrawlResponse>("/api/zalo/crawl", {
    method: "POST",
    headers: buildHeaders({
      "X-Session-ID": payload.sessionId,
    }),
    body: JSON.stringify({
      group_name: payload.group_name.trim(),
      sheet_tab: payload.sheet_tab?.trim() || undefined,
    }),
  });
}

export function getZaloJob(jobId: string): Promise<ZaloJobData> {
  return requestJson<ZaloJobData>(
    `/api/zalo/jobs/${encodeURIComponent(jobId)}`,
    {
      method: "GET",
    },
  );
}

export function getZaloJobs(): Promise<ZaloJobData[]> {
  return requestJson<ZaloJobData[]>("/api/zalo/jobs", {
    method: "GET",
  });
}
