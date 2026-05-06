import { API_BASE_URL, API_KEY } from "@/lib/env";
import type {
  AddN8nGroupRequest,
  CrawlGroupRequest,
  CrawlResponse,
  FilterDataRequest,
  FilterDataResponse,
  GetAllN8nGroupsRequest,
  GetAllPostsRequest,
  GetAllPostsResponse,
  LoginRequest,
  LoginResponse,
  N8nGroupOperationResponse,
  RemoveN8nGroupRequest,
  StartWorkflowRequest,
  StartWorkflowResponse,
  StatusResponse,
  UpdateN8nGroupRequest,
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

export function getAllN8nGroups(
  payload: GetAllN8nGroupsRequest,
): Promise<N8nGroupOperationResponse> {
  return requestJson<N8nGroupOperationResponse>("/groups/n8n-get-all", {
    method: "POST",
    body: JSON.stringify({ email: payload.email.trim() }),
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
