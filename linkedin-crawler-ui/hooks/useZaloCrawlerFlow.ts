"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { API_BASE_URL, API_KEY } from "@/lib/env";
import {
  buildZaloJobEventsUrl,
  createZaloAccount,
  deleteAllZaloSessions,
  deleteZaloAccount,
  getDefaultZaloWorkerId,
  getZaloAccounts,
  getZaloCrawledGroups,
  getZaloCurrentStatus,
  getZaloWorkers,
  initZaloAuthSession,
  refreshZaloLoginQr,
  resumeZaloManualLogin,
  startZaloManualLogin,
  getZaloJobs,
  startZaloCrawl,
  verifyZaloGroups,
  updateZaloAccount,
} from "@/services/zaloCrawlerService";
import type {
  ZaloAccountInfo,
  ZaloAuthStatus,
  ZaloCrawledGroupItem,
  ZaloCrawledGroupsResponse,
  ZaloCurrentStatusResponse,
  ZaloJobData,
  ZaloJobProgress,
  ZaloJobStatus,
  ZaloMessage,
  ZaloGroupVerifyStatus,
  ZaloWorkerInfo,
} from "@/types/zalo-api";

const AUTH_POLL_INTERVAL_MS = 2000;
const JOB_POLL_INTERVAL_MS = 2500;
const JOB_STALL_TIMEOUT_MS = 45000;
const RESUME_RETRY_ATTEMPTS = 20;
const RESUME_RETRY_INTERVAL_MS = 2000;
const ZALO_USER_ID_STORAGE_KEY = "zalo_crawler_user_id";
const LINKEDIN_EMAIL_STORAGE_KEY = "linkedin_crawler_email";
const ZALO_ACCOUNT_OWNER_ID = "default";
const INITIAL_GROUP_ROW_ID = "zalo-group-0";

const MSG_LOAD_CRAWLED_GROUPS_ERROR = "Kh\u00f4ng th\u1ec3 t\u1ea3i danh s\u00e1ch nh\u00f3m \u0111\u00e3 crawl.";
const MSG_CHECK_LOGIN_ERROR = "Kh\u00f4ng th\u1ec3 ki\u1ec3m tra tr\u1ea1ng th\u00e1i \u0111\u0103ng nh\u1eadp Zalo.";
const MSG_UPDATE_PROGRESS_ERROR = "Kh\u00f4ng th\u1ec3 c\u1eadp nh\u1eadt ti\u1ebfn \u0111\u1ed9 crawl Zalo.";
const MSG_MANUAL_OPENED =
  "Đã mở màn hình Zalo remote. Hãy đăng nhập hoặc xử lý xác minh bổ sung rồi quay lại màn monitor.";
const MSG_QR_READY =
  "Mã QR Zalo đã sẵn sàng. Hãy quét QR và đợi hệ thống xác nhận đăng nhập.";
const MSG_MANUAL_RESUME_WAITING =
  "Phiên Zalo chưa sẵn sàng. Hãy hoàn tất thao tác xác minh rồi thử lại.";
const MSG_GROUP_ADDED = "\u0110\u00e3 th\u00eam nh\u00f3m v\u00e0o danh s\u00e1ch crawl.";
const MSG_GROUP_EXISTS = "Nh\u00f3m n\u00e0y \u0111\u00e3 c\u00f3 trong danh s\u00e1ch crawl.";
const MSG_LOGIN_REQUIRED =
  "C\u1ea7n ho\u00e0n t\u1ea5t \u0111\u0103ng nh\u1eadp Zalo tr\u01b0\u1edbc khi ch\u1ea1y crawl.";
const MSG_GROUP_REQUIRED =
  "Th\u00eam \u00edt nh\u1ea5t m\u1ed9t t\u00ean nh\u00f3m Zalo tr\u01b0\u1edbc khi ch\u1ea1y crawl.";
const MSG_GROUP_VERIFY_REQUIRED =
  "Kiểm tra nhóm trước khi chạy crawl. Chỉ nhóm đã xác minh mới được chạy.";
const MSG_CRAWL_QUEUE_BUSY =
  "Đang có job crawl trong hàng chờ hoặc đang chạy. Hãy chờ job hiện tại xong rồi chạy tiếp để tránh trộn nhóm.";
const MSG_JOB_INIT_ERROR = "Kh\u00f4ng th\u1ec3 kh\u1edfi t\u1ea1o job crawl.";
const MSG_ALL_JOB_INIT_ERROR =
  "Kh\u00f4ng th\u1ec3 t\u1ea1o job crawl n\u00e0o. Ki\u1ec3m tra l\u1ed7i chi ti\u1ebft theo t\u1eebng nh\u00f3m.";
const MSG_SESSION_ENDED = "\u0110\u00e3 k\u1ebft th\u00fac phi\u00ean Zalo.";
const MSG_CLOSE_SESSION_ERROR = "Kh\u00f4ng th\u1ec3 \u0111\u00f3ng phi\u00ean Zalo tr\u00ean server.";

export interface ZaloGroupInputRow {
  id: string;
  groupName: string;
  sheetTab: string;
  verifyStatus: ZaloGroupVerifyStatus;
  verifyMessage?: string | null;
  verifiedGroupId?: string | null;
  memberCount?: number | null;
  messageCount?: number;
  warnings?: string[];
}

export interface ZaloTrackedJobState {
  rowId: string;
  jobId: string;
  groupName: string;
  sheetTab: string;
  status: ZaloJobStatus;
  progress: ZaloJobProgress;
  sheetUrl: string | null;
  sheetId: string | null;
  startedAt: string | null;
  completedAt: string | null;
  error: string | null;
  messages: ZaloMessage[];
  lastChangedAt: number;
  lastSeenAt: number;
  stalled: boolean;
  isLocalOnly?: boolean;
}

export interface ZaloCrawlerSummary {
  total: number;
  queued: number;
  running: number;
  completed: number;
  failed: number;
  totalMessages: number;
  totalImages: number;
  overallProgressPercent: number;
}

export interface ZaloCrawlerFlowValue {
  userId: string;
  selectedWorkerId: string;
  workers: ZaloWorkerInfo[];
  accounts: ZaloAccountInfo[];
  isLoadingWorkers: boolean;
  isLoadingAccounts: boolean;
  workersError: string | null;
  accountsError: string | null;
  sessionId: string | null;
  authStatus: ZaloAuthStatus;
  isCheckingLoginStatus: boolean;
  isStartingSession: boolean;
  isOpeningManualScreen: boolean;
  isSubmittingGroups: boolean;
  isVerifyingGroups: boolean;
  isResumingSession: boolean;
  isEndingSession: boolean;
  feedbackMessage: string | null;
  errorMessage: string | null;
  warningMessage: string | null;
  loginUrl: string | null;
  manualViewerUrl: string | null;
  qrBase64: string | null;
  qrImageUrl: string | null;
  isLoggedIn: boolean;
  canCrawl: boolean;
  sessionExpired: boolean;
  crawledGroups: ZaloCrawledGroupItem[];
  crawledGroupsSheetUrl: string | null;
  crawledGroupsTotal: number;
  isLoadingCrawledGroups: boolean;
  crawledGroupsError: string | null;
  groupRows: ZaloGroupInputRow[];
  jobs: ZaloTrackedJobState[];
  summary: ZaloCrawlerSummary;
  canLaunchJobs: boolean;
  hasConfirmedSession: boolean;
  maxMessagesPerGroup: number;
  setMaxMessagesPerGroup: (value: number) => void;
  switchWorker: (workerId: string) => void;
  switchAccount: (accountId: string) => void;
  refreshLoginStatus: () => Promise<void>;
  createAccount: (label: string, phone?: string) => Promise<void>;
  deleteAccount: (accountId: string, deleteAuth?: boolean) => Promise<void>;
  updateAccount: (accountId: string, label: string, phone?: string) => Promise<void>;
  startSession: () => Promise<void>;
  openManualScreen: () => Promise<void>;
  resumeManualLogin: () => Promise<void>;
  addGroupRow: () => void;
  addCrawledGroup: (group: ZaloCrawledGroupItem) => void;
  updateGroupRow: (
    rowId: string,
    field: "groupName" | "sheetTab",
    value: string,
  ) => void;
  removeGroupRow: (rowId: string) => void;
  verifyGroupRows: () => Promise<void>;
  startCrawlForGroups: () => Promise<void>;
  retryGroup: (rowId: string) => Promise<void>;
  endSession: () => Promise<void>;
  restartSession: () => Promise<void>;
}

function createGroupRow(seed = 0): ZaloGroupInputRow {
  return {
    id: seed === 0 ? INITIAL_GROUP_ROW_ID : `zalo-group-${seed}`,
    groupName: "",
    sheetTab: "",
    verifyStatus: "unchecked",
    verifyMessage: null,
    verifiedGroupId: null,
    memberCount: null,
    messageCount: 0,
    warnings: [],
  };
}

function emptyProgress(): ZaloJobProgress {
  return {
    messages_collected: 0,
    images_found: 0,
    oldest_message_date: null,
  };
}

function buildJobSignature(
  job: Pick<
    ZaloTrackedJobState,
    "status" | "progress" | "sheetUrl" | "completedAt" | "error" | "messages"
  >,
): string {
  return JSON.stringify({
    status: job.status,
    progress: job.progress,
    sheetUrl: job.sheetUrl,
    completedAt: job.completedAt,
    error: job.error,
    messages: job.messages,
  });
}

function normalizeMessages(messages: ZaloJobData["messages"]): ZaloMessage[] {
  if (!Array.isArray(messages)) return [];

  return messages.filter(
    (message): message is ZaloMessage =>
      Boolean(message) &&
      typeof message.sender === "string" &&
      typeof message.time_text === "string" &&
      typeof message.content === "string",
  );
}

function sanitizeRows(rows: ZaloGroupInputRow[]): ZaloGroupInputRow[] {
  return rows
    .map((row) => ({
      ...row,
      groupName: row.groupName.trim(),
      sheetTab: row.sheetTab.trim(),
      verifyStatus: row.verifyStatus,
      verifyMessage: row.verifyMessage ?? null,
      verifiedGroupId: row.verifiedGroupId ?? null,
      memberCount: row.memberCount ?? null,
      messageCount: row.messageCount ?? 0,
      warnings: row.warnings ?? [],
    }))
    .filter((row) => row.groupName.length > 0);
}

function makeLocalFailedJob(
  row: ZaloGroupInputRow,
  message: string,
): ZaloTrackedJobState {
  const now = Date.now();

  return {
    rowId: row.id,
    jobId: `failed-${row.id}-${now}`,
    groupName: row.groupName,
    sheetTab: row.sheetTab || row.groupName,
    status: "failed",
    progress: emptyProgress(),
    sheetUrl: null,
    sheetId: null,
    startedAt: new Date(now).toISOString(),
    completedAt: new Date(now).toISOString(),
    error: message,
    messages: [],
    lastChangedAt: now,
    lastSeenAt: now,
    stalled: false,
    isLocalOnly: true,
  };
}

function makeJobState(
  row: ZaloGroupInputRow,
  response: { job_id: string; sheet_url: string | null; status?: "queued" | "running" },
): ZaloTrackedJobState {
  const now = Date.now();

  return {
    rowId: row.id,
    jobId: response.job_id,
    groupName: row.groupName,
    sheetTab: row.sheetTab || row.groupName,
    status: response.status ?? "running",
    progress: emptyProgress(),
    sheetUrl: response.sheet_url ?? null,
    sheetId: null,
    startedAt: new Date(now).toISOString(),
    completedAt: null,
    error: null,
    messages: [],
    lastChangedAt: now,
    lastSeenAt: now,
    stalled: false,
  };
}

function isActiveJobStatus(status: ZaloJobStatus): boolean {
  return status === "queued" || status === "running";
}

function mergeRemoteJob(
  previous: ZaloTrackedJobState,
  job: ZaloJobData,
  now: number,
): ZaloTrackedJobState {
  const nextBase: ZaloTrackedJobState = {
    ...previous,
    groupName: job.group_name || previous.groupName,
    sheetTab: job.sheet_tab || previous.sheetTab,
    status: job.status,
    progress: job.progress ?? previous.progress,
    sheetUrl: job.sheet_url ?? previous.sheetUrl,
    sheetId: job.sheet_id ?? previous.sheetId,
    startedAt: job.started_at ?? previous.startedAt,
    completedAt: job.completed_at ?? previous.completedAt,
    error: job.error ?? null,
    messages: normalizeMessages(job.messages),
    lastSeenAt: now,
  };

  const previousSignature = buildJobSignature(previous);
  const nextSignature = buildJobSignature(nextBase);
  const hasChanged = previousSignature !== nextSignature;
  const lastChangedAt = hasChanged ? now : previous.lastChangedAt;

  return {
    ...nextBase,
    lastChangedAt,
    stalled:
      isActiveJobStatus(nextBase.status) &&
      now - lastChangedAt >= JOB_STALL_TIMEOUT_MS,
  };
}

function mapCurrentStatusToAuthStatus(
  payload: ZaloCurrentStatusResponse,
): ZaloAuthStatus {
  if (payload.session_expired || payload.status === "session_expired") return "session_expired";
  if (payload.status === "confirmed" && payload.can_crawl) return "confirmed";
  if (payload.status === "waiting_scan") return "waiting_scan";
  if (payload.status === "qr_expired") return "qr_expired";
  return "not_logged_in";
}

function getDisplayableQrBase64(status: ZaloAuthStatus, qrBase64?: string | null): string | null {
  return status === "waiting_scan" && qrBase64 ? qrBase64 : null;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function normalizeZaloUserId(value: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "");

  return normalized || "default";
}

function humanizeZaloGroupVerifyDetail(detail: string, groupName: string): string {
  const value = detail.trim();
  const expectedMatch = value.match(/Expected group ['"](.+?)['"] but current title is ['"](.+?)['"]/i);
  if (expectedMatch) {
    const expected = expectedMatch[1] || groupName;
    const current = expectedMatch[2] || "một cuộc trò chuyện khác";
    return `Zalo vẫn đang mở "${current}", chưa chuyển sang "${expected}". Hệ thống đã dừng để tránh crawl nhầm nhóm. Hãy chờ Zalo đồng bộ xong rồi bấm "Kiểm tra nhóm" lại.`;
  }

  const conversationChangedMatch = value.match(/Conversation changed.*expected=['"](.+?)['"].*current=['"](.+?)['"]/i);
  if (conversationChangedMatch) {
    const expected = conversationChangedMatch[1] || groupName;
    const current = conversationChangedMatch[2] || "một cuộc trò chuyện khác";
    return `Trong lúc kiểm tra, Zalo chuyển sang "${current}" thay vì "${expected}". Hệ thống đã dừng để không lấy nhầm tin. Hãy không thao tác cửa sổ Zalo khi đang crawl và thử kiểm tra lại.`;
  }

  if (/avoid running multiple crawl jobs|mixing messages|currently open conversation/i.test(value)) {
    return `Zalo chưa mở đúng nhóm "${groupName}". Hệ thống đã dừng để tránh lấy nhầm tin nhắn. Hãy chờ danh sách chat tải xong rồi bấm kiểm tra lại.`;
  }

  return value || "Không xác minh được nhóm Zalo. Hãy thử kiểm tra lại sau vài giây.";
}

function readStableZaloUserId(): string {
  if (typeof window === "undefined") return "default";

  const linkedInEmail = window.localStorage.getItem(LINKEDIN_EMAIL_STORAGE_KEY);
  const emailUserId = linkedInEmail?.trim()
    ? normalizeZaloUserId(linkedInEmail)
    : "";

  const existing = window.localStorage.getItem(ZALO_USER_ID_STORAGE_KEY);
  if (existing?.trim()) {
    const existingUserId = normalizeZaloUserId(existing);
    if (
      emailUserId &&
      (existingUserId === "default" || existingUserId.startsWith("browser-"))
    ) {
      window.localStorage.setItem(ZALO_USER_ID_STORAGE_KEY, emailUserId);
      return emailUserId;
    }
    if (existingUserId === "default") {
      const browserUserId = normalizeZaloUserId(
        `browser-${globalThis.crypto?.randomUUID?.() ?? Date.now().toString(36)}`,
      );
      window.localStorage.setItem(ZALO_USER_ID_STORAGE_KEY, browserUserId);
      return browserUserId;
    }
    return existingUserId;
  }

  const seed = emailUserId || `browser-${globalThis.crypto?.randomUUID?.() ?? Date.now().toString(36)}`;
  const userId = normalizeZaloUserId(seed);
  window.localStorage.setItem(ZALO_USER_ID_STORAGE_KEY, userId);
  return userId;
}

export function useZaloCrawlerFlow(): ZaloCrawlerFlowValue {
  const [userId, setUserId] = useState("default");
  const [selectedWorkerId, setSelectedWorkerIdState] = useState(getDefaultZaloWorkerId());
  const [workers, setWorkers] = useState<ZaloWorkerInfo[]>([
    {
      id: getDefaultZaloWorkerId(),
      label: "Default",
      status: "unknown",
      is_default: true,
      queue_state: "unknown",
    },
  ]);
  const [isLoadingWorkers, setIsLoadingWorkers] = useState(true);
  const [workersError, setWorkersError] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<ZaloAccountInfo[]>([]);
  const [isLoadingAccounts, setIsLoadingAccounts] = useState(true);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [isUserIdReady, setIsUserIdReady] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [authStatus, setAuthStatus] = useState<ZaloAuthStatus>("not_logged_in");
  const [isCheckingLoginStatus, setIsCheckingLoginStatus] = useState(true);
  const [isStartingSession, setIsStartingSession] = useState(false);
  const [isOpeningManualScreen, setIsOpeningManualScreen] = useState(false);
  const [isSubmittingGroups, setIsSubmittingGroups] = useState(false);
  const [isVerifyingGroups, setIsVerifyingGroups] = useState(false);
  const [isResumingSession, setIsResumingSession] = useState(false);
  const [isEndingSession, setIsEndingSession] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [warningMessage, setWarningMessage] = useState<string | null>(null);
  const [loginUrl, setLoginUrl] = useState<string | null>(null);
  const [manualViewerUrl, setManualViewerUrl] = useState<string | null>(null);
  const [qrBase64, setQrBase64] = useState<string | null>(null);
  const [qrImageUrl, setQrImageUrl] = useState<string | null>(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [canCrawl, setCanCrawl] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [crawledGroups, setCrawledGroups] = useState<ZaloCrawledGroupItem[]>([]);
  const [crawledGroupsSheetUrl, setCrawledGroupsSheetUrl] =
    useState<string | null>(null);
  const [crawledGroupsTotal, setCrawledGroupsTotal] = useState(0);
  const [isLoadingCrawledGroups, setIsLoadingCrawledGroups] = useState(true);
  const [crawledGroupsError, setCrawledGroupsError] = useState<string | null>(
    null,
  );
  const [groupRows, setGroupRows] = useState<ZaloGroupInputRow[]>(() => [
    createGroupRow(0),
  ]);
  const [jobsByRow, setJobsByRow] = useState<Record<string, ZaloTrackedJobState>>(
    {},
  );
  const [maxMessagesPerGroup, setMaxMessagesPerGroupState] = useState(50);

  const authIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const jobIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const authEventSourceRef = useRef<EventSource | null>(null);
  const jobEventSourceRef = useRef<EventSource | null>(null);
  const manualViewerWindowRef = useRef<Window | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const activeJobIdsRef = useRef<string[]>([]);
  const previousActiveJobCountRef = useRef(0);

  useEffect(() => {
    queueMicrotask(() => {
      setUserId(readStableZaloUserId());
      setIsUserIdReady(true);
    });
  }, [userId]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const clearAuthPolling = useCallback(() => {
    if (authIntervalRef.current) {
      clearInterval(authIntervalRef.current);
      authIntervalRef.current = null;
    }
  }, []);

  const clearJobPolling = useCallback(() => {
    if (jobIntervalRef.current) {
      clearInterval(jobIntervalRef.current);
      jobIntervalRef.current = null;
    }
  }, []);

  const clearAuthEventStream = useCallback(() => {
    if (authEventSourceRef.current) {
      authEventSourceRef.current.close();
      authEventSourceRef.current = null;
    }
  }, []);

  const clearJobEventStream = useCallback(() => {
    if (jobEventSourceRef.current) {
      jobEventSourceRef.current.close();
      jobEventSourceRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearAuthPolling();
      clearJobPolling();
      clearAuthEventStream();
      clearJobEventStream();
    };
  }, [clearAuthEventStream, clearAuthPolling, clearJobEventStream, clearJobPolling]);

  const loadWorkers = useCallback(async () => {
    setIsLoadingWorkers(true);
    setWorkersError(null);
    try {
      const response = await getZaloWorkers(userId);
      const nextWorkers =
        response.workers.length > 0
          ? response.workers
          : [
              {
                id: getDefaultZaloWorkerId(),
                label: "Default",
                status: "unknown",
                is_default: true,
                queue_state: "unknown",
              },
            ];
      setWorkers(nextWorkers);

      const availableIds = new Set(nextWorkers.map((worker) => worker.id));
      const backendSelected = response.selected_worker_id ?? nextWorkers[0]?.id ?? getDefaultZaloWorkerId();
      const nextSelected = availableIds.has(backendSelected)
        ? backendSelected
        : nextWorkers[0]?.id ?? getDefaultZaloWorkerId();
      setSelectedWorkerIdState(nextSelected);
    } catch (error) {
      setWorkersError(error instanceof Error ? error.message : "Không thể tải danh sách account Zalo.");
      setWorkers([
        {
          id: getDefaultZaloWorkerId(),
          label: "Default",
          status: "unknown",
          is_default: true,
          queue_state: "unknown",
        },
      ]);
      setSelectedWorkerIdState(getDefaultZaloWorkerId());
    } finally {
      setIsLoadingWorkers(false);
    }
  }, [userId]);

  const loadAccounts = useCallback(async () => {
    setIsLoadingAccounts(true);
    setAccountsError(null);
    try {
      const response = await getZaloAccounts(ZALO_ACCOUNT_OWNER_ID);
      setAccounts(response.accounts ?? []);
    } catch (error) {
      setAccountsError(error instanceof Error ? error.message : "Không thể tải danh sách tài khoản Zalo.");
    } finally {
      setIsLoadingAccounts(false);
    }
  }, []);

  useEffect(() => {
    if (!isUserIdReady) return;
    void loadWorkers();
    void loadAccounts();
    const intervalId = setInterval(() => {
      void loadWorkers();
      void loadAccounts();
    }, 30000);
    return () => clearInterval(intervalId);
  }, [isUserIdReady, loadAccounts, loadWorkers]);

  const loadCrawledGroups = useCallback(async () => {
    if (!isUserIdReady) return;

    setIsLoadingCrawledGroups(true);
    setCrawledGroupsError(null);

    try {
      const response: ZaloCrawledGroupsResponse = await getZaloCrawledGroups(userId);
      setCrawledGroups(response.groups ?? []);
      setCrawledGroupsSheetUrl(response.sheet_url ?? null);
      setCrawledGroupsTotal(response.total_groups ?? response.groups?.length ?? 0);
    } catch (error) {
      setCrawledGroupsError(
        error instanceof Error
          ? `${MSG_LOAD_CRAWLED_GROUPS_ERROR} ${error.message}`
          : MSG_LOAD_CRAWLED_GROUPS_ERROR,
      );
    } finally {
      setIsLoadingCrawledGroups(false);
    }
  }, [isUserIdReady, userId]);

  useEffect(() => {
    const timerId = setTimeout(() => {
      void loadCrawledGroups();
    }, 0);

    return () => clearTimeout(timerId);
  }, [loadCrawledGroups]);

  const resetAuthState = useCallback(() => {
    setSessionId(null);
    setAuthStatus("not_logged_in");
    setIsLoggedIn(false);
    setCanCrawl(false);
    setQrBase64(null);
    setQrImageUrl(null);
  }, []);

  const switchWorker = useCallback((_workerId: string) => {
    // Worker routing is automatic by user_id; keep this no-op for compatibility.
  }, []);

  const switchAccount = useCallback((accountId: string) => {
    const nextUserId = normalizeZaloUserId(accountId);
    if (!nextUserId || nextUserId === userId) return;
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ZALO_USER_ID_STORAGE_KEY, nextUserId);
    }
    clearAuthPolling();
    clearJobPolling();
    clearAuthEventStream();
    clearJobEventStream();
    setUserId(nextUserId);
    resetAuthState();
    setJobsByRow({});
    setGroupRows([createGroupRow(0)]);
    setCrawledGroups([]);
    setCrawledGroupsTotal(0);
    setFeedbackMessage(null);
    setWarningMessage(null);
    setErrorMessage(null);
  }, [clearAuthEventStream, clearAuthPolling, clearJobEventStream, clearJobPolling, resetAuthState, userId]);

  const createAccount = useCallback(async (label: string, phone?: string) => {
    const cleanLabel = label.trim();
    if (!cleanLabel) {
      setErrorMessage("Nhập tên tài khoản Zalo trước.");
      return;
    }
    setAccountsError(null);
    try {
      const accountId = normalizeZaloUserId(cleanLabel);
      await createZaloAccount({
        account_id: accountId,
        owner_id: ZALO_ACCOUNT_OWNER_ID,
        label: cleanLabel,
        phone: phone?.trim() || undefined,
      });
      await loadAccounts();
      switchAccount(accountId);
    } catch (error) {
      setAccountsError(error instanceof Error ? error.message : "Không thể tạo tài khoản Zalo.");
    }
  }, [loadAccounts, switchAccount]);

  const deleteAccount = useCallback(async (accountId: string, deleteAuth = false) => {
    const safeAccountId = normalizeZaloUserId(accountId);
    try {
      await deleteZaloAccount(safeAccountId, deleteAuth);
      await loadAccounts();
      if (safeAccountId === userId) {
        switchAccount("default");
      }
    } catch (error) {
      setAccountsError(error instanceof Error ? error.message : "Không thể xóa tài khoản Zalo.");
    }
  }, [loadAccounts, switchAccount, userId]);

  const updateAccount = useCallback(async (accountId: string, label: string, phone?: string) => {
    const cleanLabel = label.trim();
    if (!cleanLabel) {
      setErrorMessage("Nhập tên tài khoản Zalo trước.");
      return;
    }
    setAccountsError(null);
    try {
      const safeAccountId = normalizeZaloUserId(accountId);
      await updateZaloAccount(safeAccountId, {
        label: cleanLabel,
        phone: phone?.trim() || undefined,
      });
      await loadAccounts();
    } catch (error) {
      setAccountsError(error instanceof Error ? error.message : "Không thể cập nhật tài khoản Zalo.");
    }
  }, [loadAccounts]);

  const applyAuthStatus = useCallback((statusResponse: ZaloCurrentStatusResponse) => {
    setSessionId(statusResponse.session_id);
    setLoginUrl(statusResponse.login_url);
    setManualViewerUrl(statusResponse.manual_viewer_url ?? null);
    const nextAuthStatus = mapCurrentStatusToAuthStatus(statusResponse);
    const expired = nextAuthStatus === "session_expired";
    setSessionExpired(expired);
    // Phiên hết hạn => coi như chưa đăng nhập để UI hiện lại flow QR.
    setIsLoggedIn(expired ? false : statusResponse.is_logged_in);
    setCanCrawl(expired ? false : statusResponse.can_crawl);
    setAuthStatus(nextAuthStatus);
    // Only update QR when the response provides a new one, or clear it on confirmed/expired.
    // During "waiting_scan" without qr_base64 in the polling response, preserve the existing QR
    // so it doesn't flicker or disappear between polls.
    if (statusResponse.qr_base64) {
      setQrBase64(statusResponse.qr_base64);
      setQrImageUrl(null);
    } else if (
      nextAuthStatus === "confirmed" ||
      nextAuthStatus === "qr_expired" ||
      nextAuthStatus === "session_expired"
    ) {
      setQrBase64(null);
      setQrImageUrl(null);
    }
    setWarningMessage(
      expired
        ? "Phiên đăng nhập Zalo đã hết hạn. Vui lòng đăng nhập lại bằng mã QR."
        : null,
    );
  }, []);

  const pollAuthStatus = useCallback(async () => {
    if (!isUserIdReady) return;

    try {
      const statusResponse = await getZaloCurrentStatus(userId);
      applyAuthStatus(statusResponse);
    } catch (error) {
      setWarningMessage(
        error instanceof Error
          ? `${MSG_CHECK_LOGIN_ERROR} ${error.message}`
          : MSG_CHECK_LOGIN_ERROR,
      );
    }
  }, [applyAuthStatus, isUserIdReady, userId]);

  useEffect(() => {
    if (!isUserIdReady) return;

    const timerId = setTimeout(() => {
      void pollAuthStatus().finally(() => setIsCheckingLoginStatus(false));
    }, 0);

    authIntervalRef.current = setInterval(() => {
      void pollAuthStatus();
    }, AUTH_POLL_INTERVAL_MS);

    return () => {
      clearTimeout(timerId);
      clearAuthPolling();
    };
  }, [clearAuthPolling, isUserIdReady, pollAuthStatus]);

  useEffect(() => {
    if (!isUserIdReady) return;

    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }

    clearAuthEventStream();
    const streamParams = new URLSearchParams({ user_id: userId });
    if (API_KEY) streamParams.set("api_key", API_KEY);
    const streamUrl = `${API_BASE_URL}/api/zalo/auth/events?${streamParams.toString()}`;
    const eventSource = new EventSource(streamUrl, { withCredentials: true });
    authEventSourceRef.current = eventSource;

    const onAuthStatus = (event: Event) => {
      try {
        const messageEvent = event as MessageEvent;
        const data = JSON.parse(messageEvent.data) as ZaloCurrentStatusResponse;
        applyAuthStatus(data);
      } catch {
        // ignore malformed payload
      }
    };

    eventSource.addEventListener("auth-status", onAuthStatus);
    eventSource.onerror = () => {
      // keep polling fallback active
    };

    return () => {
      eventSource.removeEventListener("auth-status", onAuthStatus);
      clearAuthEventStream();
    };
  }, [applyAuthStatus, clearAuthEventStream, isUserIdReady, userId]);

  const applyRemoteJob = useCallback((remoteJob: ZaloJobData) => {
    const now = Date.now();
    setJobsByRow((previous) => {
      let hasChanges = false;
      const next: Record<string, ZaloTrackedJobState> = { ...previous };

      for (const [rowId, jobState] of Object.entries(previous)) {
        if (jobState.jobId !== remoteJob.job_id || jobState.isLocalOnly) {
          continue;
        }

        const mergedJob = mergeRemoteJob(jobState, remoteJob, now);
        if (
          buildJobSignature(jobState) !== buildJobSignature(mergedJob) ||
          jobState.stalled !== mergedJob.stalled
        ) {
          next[rowId] = mergedJob;
          hasChanges = true;
        }
      }

      return hasChanges ? next : previous;
    });
  }, []);

  useEffect(() => {
    if (!isUserIdReady) return;

    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }

    clearJobEventStream();
    const eventSource = new EventSource(buildZaloJobEventsUrl(userId), {
      withCredentials: true,
    });
    jobEventSourceRef.current = eventSource;

    const onJobStatus = (event: Event) => {
      try {
        const messageEvent = event as MessageEvent;
        const data = JSON.parse(messageEvent.data) as ZaloJobData;
        applyRemoteJob(data);
      } catch {
        // ignore malformed payload
      }
    };

    eventSource.addEventListener("job-status", onJobStatus);
    eventSource.onerror = () => {
      // keep polling fallback active
    };

    return () => {
      eventSource.removeEventListener("job-status", onJobStatus);
      clearJobEventStream();
    };
  }, [applyRemoteJob, clearJobEventStream, isUserIdReady, userId]);

  const pollRunningJobs = useCallback(async () => {
    const activeJobIds = activeJobIdsRef.current;
    if (activeJobIds.length === 0) return;

    try {
      const jobs = await getZaloJobs(userId);
      const jobsById = new Map(jobs.map((job) => [job.job_id, job]));
      const now = Date.now();

      setJobsByRow((previous) => {
        let hasChanges = false;
        const next: Record<string, ZaloTrackedJobState> = { ...previous };

        for (const [rowId, jobState] of Object.entries(previous)) {
          if (!isActiveJobStatus(jobState.status) || jobState.isLocalOnly) {
            continue;
          }

          const remoteJob = jobsById.get(jobState.jobId);
          if (!remoteJob) {
            const stalled = now - jobState.lastChangedAt >= JOB_STALL_TIMEOUT_MS;
            if (stalled !== jobState.stalled) {
              next[rowId] = {
                ...jobState,
                stalled,
                lastSeenAt: now,
              };
              hasChanges = true;
            }
            continue;
          }

          const mergedJob = mergeRemoteJob(jobState, remoteJob, now);
          if (
            buildJobSignature(jobState) !== buildJobSignature(mergedJob) ||
            jobState.stalled !== mergedJob.stalled
          ) {
            next[rowId] = mergedJob;
            hasChanges = true;
          }
        }

        return hasChanges ? next : previous;
      });

      setWarningMessage(null);
    } catch (error) {
      setWarningMessage(
        error instanceof Error
          ? `${MSG_UPDATE_PROGRESS_ERROR} ${error.message}`
          : MSG_UPDATE_PROGRESS_ERROR,
      );
    }
  }, []);

  const jobs = useMemo(() => {
    return Object.values(jobsByRow).sort((left, right) => {
      const leftTime = left.startedAt ? Date.parse(left.startedAt) : 0;
      const rightTime = right.startedAt ? Date.parse(right.startedAt) : 0;
      return rightTime - leftTime;
    });
  }, [jobsByRow]);

  const activeJobIds = useMemo(() => {
    return jobs
      .filter((job) => isActiveJobStatus(job.status) && !job.isLocalOnly)
      .map((job) => job.jobId);
  }, [jobs]);

  useEffect(() => {
    const previousActiveJobCount = previousActiveJobCountRef.current;
    activeJobIdsRef.current = activeJobIds;
    previousActiveJobCountRef.current = activeJobIds.length;
    clearJobPolling();

    if (activeJobIds.length === 0) {
      if (previousActiveJobCount > 0) {
        void loadCrawledGroups();
      }
      return;
    }

    void pollRunningJobs();

    jobIntervalRef.current = setInterval(() => {
      void pollRunningJobs();
    }, JOB_POLL_INTERVAL_MS);

    return clearJobPolling;
  }, [activeJobIds, clearJobPolling, loadCrawledGroups, pollRunningJobs]);

  const openManualScreen = useCallback(async () => {
    setErrorMessage(null);
    setWarningMessage(null);
    setIsOpeningManualScreen(true);
    try {
      const response = await startZaloManualLogin(userId);
      setSessionId(response.session_id);
      setAuthStatus(response.status);
      setIsLoggedIn(response.can_crawl);
      setCanCrawl(response.can_crawl);
      const viewerUrl = response.manual_viewer_url ?? manualViewerUrl;
      if (viewerUrl) {
        manualViewerWindowRef.current = window.open(
          viewerUrl,
          "_blank",
          "noopener,noreferrer",
        );
      }
      setFeedbackMessage(MSG_MANUAL_OPENED);
      void pollAuthStatus();
    } catch (error) {
      setWarningMessage(
        error instanceof Error
          ? `${MSG_CHECK_LOGIN_ERROR} ${error.message}`
          : MSG_CHECK_LOGIN_ERROR,
      );
    } finally {
      setIsOpeningManualScreen(false);
    }
  }, [manualViewerUrl, pollAuthStatus, userId]);

  const startSession = useCallback(async () => {
    setErrorMessage(null);
    setWarningMessage(null);
    setIsStartingSession(true);
    try {
      const response = await initZaloAuthSession(userId);
      const qrBase64 = getDisplayableQrBase64(response.status, response.qr_base64);
      setSessionId(response.session_id);
      setAuthStatus(response.status);
      setIsLoggedIn(response.status === "confirmed");
      setCanCrawl(response.status === "confirmed");
      setQrBase64(qrBase64);
      setQrImageUrl(null);
      setFeedbackMessage(response.status === "confirmed" ? null : MSG_QR_READY);
      void pollAuthStatus();
    } catch (error) {
      setWarningMessage(
        error instanceof Error
          ? `${MSG_CHECK_LOGIN_ERROR} ${error.message}`
          : MSG_CHECK_LOGIN_ERROR,
      );
    } finally {
      setIsStartingSession(false);
    }
  }, [pollAuthStatus, userId]);

  const resumeManualLogin = useCallback(async () => {
    setErrorMessage(null);
    setWarningMessage(null);
    setIsResumingSession(true);
    try {
      for (let attempt = 0; attempt < RESUME_RETRY_ATTEMPTS; attempt += 1) {
        const response = await resumeZaloManualLogin(userId);
        setSessionId(response.session_id);
        setAuthStatus(response.status);
        setIsLoggedIn(response.can_crawl);
        setCanCrawl(response.can_crawl);
        if (response.can_crawl) {
          setFeedbackMessage(
            "Phiên Zalo đã sẵn sàng. Listener sẽ tự lưu tin nhắn mới.",
          );
          void pollAuthStatus();
          return;
        }
        if (attempt < RESUME_RETRY_ATTEMPTS - 1) {
          await sleep(RESUME_RETRY_INTERVAL_MS);
        }
      }

      setWarningMessage(MSG_MANUAL_RESUME_WAITING);
      void pollAuthStatus();
    } catch (error) {
      setWarningMessage(
        error instanceof Error
          ? `${MSG_CHECK_LOGIN_ERROR} ${error.message}`
          : MSG_CHECK_LOGIN_ERROR,
      );
    } finally {
      setIsResumingSession(false);
    }
  }, [pollAuthStatus, userId]);




  const addGroupRow = useCallback(() => {
    setGroupRows((previous) => {
      const nextSeed = previous.length;
      return [
        ...previous,
        {
          id: `zalo-group-${nextSeed}-${(typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36))}`,
          groupName: "",
          sheetTab: "",
          verifyStatus: "unchecked",
          verifyMessage: null,
          verifiedGroupId: null,
          memberCount: null,
          messageCount: 0,
          warnings: [],
        },
      ];
    });
  }, []);

  const addCrawledGroup = useCallback((group: ZaloCrawledGroupItem) => {
    const groupName = group.group_name.trim();
    const sheetTab = group.sheet_tab.trim();

    if (!groupName) return;
    let didAdd = false;

    setGroupRows((previous) => {
      const hasExisting = previous.some(
        (row) => row.groupName.trim().toLowerCase() === groupName.toLowerCase(),
      );
      if (hasExisting) {
        return previous;
      }

      const emptyIndex = previous.findIndex(
        (row) => row.groupName.trim().length === 0,
      );

      didAdd = true;

      if (emptyIndex >= 0) {
        return previous.map((row, index) =>
          index === emptyIndex
            ? {
                ...row,
                groupName,
                sheetTab: sheetTab || row.sheetTab,
                verifyStatus: "unchecked",
                verifyMessage: "Chưa kiểm tra nhóm.",
                verifiedGroupId: null,
                memberCount: null,
                messageCount: 0,
                warnings: [],
              }
            : row,
        );
      }

      return [
        ...previous,
        {
<<<<<<< HEAD
          id: `zalo-group-${previous.length}-${(typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36))}`,
=======
          id: `zalo-group-${previous.length}-${globalThis.crypto?.randomUUID?.() ?? Date.now().toString(36)}`,
>>>>>>> 6b16e686e98426109380f125cb80bddbbd4d6f08
          groupName,
          sheetTab,
          verifyStatus: "unchecked",
          verifyMessage: "Chưa kiểm tra nhóm.",
          verifiedGroupId: null,
          memberCount: null,
          messageCount: 0,
          warnings: [],
        },
      ];
    });

    if (didAdd) {
      setWarningMessage(null);
      setFeedbackMessage(MSG_GROUP_ADDED);
    } else {
      setFeedbackMessage(null);
      setWarningMessage(MSG_GROUP_EXISTS);
    }
  }, []);

  const updateGroupRow = useCallback(
    (rowId: string, field: "groupName" | "sheetTab", value: string) => {
      setGroupRows((previous) =>
        previous.map((row) =>
          row.id === rowId
            ? {
                ...row,
                [field]: value,
                verifyStatus: field === "groupName" ? "unchecked" : row.verifyStatus,
                verifyMessage: field === "groupName" ? "Chưa kiểm tra nhóm." : row.verifyMessage,
                verifiedGroupId: field === "groupName" ? null : row.verifiedGroupId,
                memberCount: field === "groupName" ? null : row.memberCount,
                messageCount: field === "groupName" ? 0 : row.messageCount,
                warnings: field === "groupName" ? [] : row.warnings,
              }
            : row,
        ),
      );
    },
    [],
  );

  const removeGroupRow = useCallback((rowId: string) => {
    setGroupRows((previous) => {
      if (previous.length <= 1) {
        return previous.map((row) =>
          row.id === rowId ? createGroupRow(0) : row,
        );
      }

      return previous.filter((row) => row.id !== rowId);
    });

    setJobsByRow((previous) => {
      if (!(rowId in previous)) return previous;
      const next = { ...previous };
      delete next[rowId];
      return next;
    });
  }, [userId]);

  const setMaxMessagesPerGroup = useCallback((value: number) => {
    const safeValue = Math.max(1, Math.min(Number.isFinite(value) ? Math.round(value) : 50, 500));
    setMaxMessagesPerGroupState(safeValue);
  }, []);

  const verifyGroupRows = useCallback(async () => {
    const currentSessionId = sessionIdRef.current;
    if (!canCrawl) {
      setErrorMessage(MSG_LOGIN_REQUIRED);
      return;
    }

    const cleanedRows = sanitizeRows(groupRows);
    if (cleanedRows.length === 0) {
      setErrorMessage(MSG_GROUP_REQUIRED);
      return;
    }

    setIsVerifyingGroups(true);
    setErrorMessage(null);
    setWarningMessage(null);
    setFeedbackMessage(`Đang kiểm tra ${cleanedRows.length} nhóm trên Zalo.`);

    try {
      const response = await verifyZaloGroups(
        userId,
        cleanedRows.map((row) => ({
          group_name: row.groupName,
          group_id: row.verifiedGroupId ?? undefined,
          sheet_tab: row.sheetTab || row.groupName,
        })),
        currentSessionId,
      );

      const verifiedByName = new Map(
        response.verified.map((item) => [item.group_name.trim().toLowerCase(), item]),
      );
      const rejectedByName = new Map(
        response.rejected.map((item) => [item.group_name.trim().toLowerCase(), item]),
      );

      setGroupRows((previous) =>
        previous.map((row) => {
          const key = row.groupName.trim().toLowerCase();
          if (!key) return row;

          const verified = verifiedByName.get(key);
          if (verified) {
            return {
              ...row,
              groupName: verified.group_name,
              sheetTab: verified.sheet_tab || row.sheetTab || verified.group_name,
              verifyStatus: "verified",
              verifyMessage: verified.warnings.includes("no_messages_synced")
                ? "Đã xác minh nhóm, nhưng hiện chưa thấy tin nhắn đã đồng bộ."
                : "Đã xác minh nhóm.",
              verifiedGroupId: verified.group_id ?? verified.group_name,
              memberCount: verified.member_count ?? null,
              messageCount: verified.message_count,
              warnings: verified.warnings,
            };
          }

          const rejected = rejectedByName.get(key);
          if (rejected) {
            return {
              ...row,
              verifyStatus: (rejected.reason as ZaloGroupVerifyStatus) || "failed",
              verifyMessage: humanizeZaloGroupVerifyDetail(rejected.detail, row.groupName),
              verifiedGroupId: null,
              memberCount: rejected.member_count ?? null,
              messageCount: 0,
              warnings: rejected.warnings,
            };
          }

          return {
            ...row,
            verifyStatus: "failed",
            verifyMessage: "Không nhận được kết quả kiểm tra từ backend.",
            verifiedGroupId: null,
            memberCount: null,
            messageCount: 0,
            warnings: [],
          };
        }),
      );

      const verifiedCount = response.verified.length;
      const rejectedCount = response.rejected.length;
      setFeedbackMessage(
        `Đã xác minh ${verifiedCount} nhóm${rejectedCount > 0 ? `, ${rejectedCount} nhóm cần kiểm tra lại` : ""}.`,
      );
      if (rejectedCount > 0) {
        setWarningMessage("Một số nhóm không đạt kiểm tra. Xem trạng thái từng dòng trước khi crawl.");
      }
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? `Không thể kiểm tra nhóm Zalo. ${error.message}`
          : "Không thể kiểm tra nhóm Zalo.",
      );
    } finally {
      setIsVerifyingGroups(false);
    }
  }, [canCrawl, groupRows, userId]);

  const launchRows = useCallback(
    async (rows: ZaloGroupInputRow[]) => {
      const currentSessionId = sessionIdRef.current;
      if (!canCrawl) {
        setErrorMessage(MSG_LOGIN_REQUIRED);
        return;
      }
      if (activeJobIdsRef.current.length > 0) {
        setErrorMessage(MSG_CRAWL_QUEUE_BUSY);
        return;
      }

      const cleanedRows = sanitizeRows(rows);
      if (cleanedRows.length === 0) {
        setErrorMessage(MSG_GROUP_REQUIRED);
        return;
      }
      const verifiedRows = cleanedRows.filter((row) => row.verifyStatus === "verified");
      if (verifiedRows.length === 0) {
        setErrorMessage(MSG_GROUP_VERIFY_REQUIRED);
        return;
      }

      const duplicateNames = new Set<string>();
      const seenNames = new Set<string>();
      for (const row of verifiedRows) {
        const normalizedName = row.groupName.toLowerCase();
        if (seenNames.has(normalizedName)) {
          duplicateNames.add(row.groupName);
        }
        seenNames.add(normalizedName);
      }

      if (duplicateNames.size > 0) {
        setErrorMessage(
          `T\u00ean nh\u00f3m b\u1ecb tr\u00f9ng: ${Array.from(duplicateNames).join(", ")}.`,
        );
        return;
      }

      setIsSubmittingGroups(true);
      setErrorMessage(null);
      setWarningMessage(null);
      setFeedbackMessage(`Đang tạo ${verifiedRows.length} job crawl. Vui lòng giữ nguyên màn hình này.`);

      const results: Array<
        | {
            ok: true;
            row: ZaloGroupInputRow;
            response: { job_id: string; sheet_url: string | null; status?: "queued" | "running" };
          }
        | { ok: false; row: ZaloGroupInputRow; message: string }
      > = [];

      for (const row of verifiedRows) {
        try {
          const response = await startZaloCrawl({
            sessionId: currentSessionId,
            userId,
            group_name: row.groupName,
            group_id: row.verifiedGroupId,
            sheet_tab: row.sheetTab || row.groupName,
            max_messages: maxMessagesPerGroup,
          });
          results.push({ ok: true, row, response });
        } catch (error) {
          results.push({
            ok: false,
            row,
            message: error instanceof Error ? error.message : MSG_JOB_INIT_ERROR,
          });
        }
      }

      setJobsByRow((previous) => {
        const next = { ...previous };
        for (const result of results) {
          next[result.row.id] = result.ok
            ? makeJobState(result.row, result.response)
            : makeLocalFailedJob(result.row, result.message);
        }
        return next;
      });

      const succeededCount = results.filter((result) => result.ok).length;
      const failedCount = results.length - succeededCount;

      if (succeededCount > 0) {
        setFeedbackMessage(
          `\u0110\u00e3 t\u1ea1o ${succeededCount} job crawl Zalo${failedCount > 0 ? `, ${failedCount} job l\u1ed7i kh\u1edfi t\u1ea1o` : ""}.`,
        );
      } else {
        setErrorMessage(MSG_ALL_JOB_INIT_ERROR);
      }

      setIsSubmittingGroups(false);
    },
    [canCrawl, maxMessagesPerGroup, userId],
  );

  const startCrawlForGroups = useCallback(async () => {
    await launchRows(groupRows);
  }, [groupRows, launchRows]);

  const retryGroup = useCallback(
    async (rowId: string) => {
      const row = groupRows.find((item) => item.id === rowId);
      if (!row) return;
      await launchRows([row]);
    },
    [groupRows, launchRows],
  );

  const endSession = useCallback(async () => {
    setIsEndingSession(true);
    setErrorMessage(null);
    setWarningMessage(null);
    try {
      await deleteAllZaloSessions(userId);
      resetAuthState();
      setJobsByRow({});
      const viewerWindow = manualViewerWindowRef.current;
      if (viewerWindow && !viewerWindow.closed) {
        try {
          viewerWindow.close();
        } catch {
          // Ignore close errors from browser restrictions.
        }
      }
      manualViewerWindowRef.current = null;
      setFeedbackMessage(MSG_SESSION_ENDED);
      void pollAuthStatus();
    } catch (error) {
      setWarningMessage(
        error instanceof Error
          ? `${MSG_CLOSE_SESSION_ERROR} ${error.message}`
          : MSG_CLOSE_SESSION_ERROR,
      );
    } finally {
      setIsEndingSession(false);
    }
  }, [pollAuthStatus, resetAuthState, userId]);

  const hasConfirmedSession = canCrawl && Boolean(sessionId);

  const restartSession = useCallback(async () => {
    if (hasConfirmedSession) {
      await endSession();
      await startSession();
      return;
    }

    setErrorMessage(null);
    setWarningMessage(null);
    setIsStartingSession(true);
    try {
      const response = await refreshZaloLoginQr(userId);
      const qrBase64 = getDisplayableQrBase64(response.status, response.qr_base64);
      setSessionId(response.session_id);
      setAuthStatus(response.status);
      setIsLoggedIn(response.status === "confirmed");
      setCanCrawl(response.status === "confirmed");
      setQrBase64(qrBase64);
      setQrImageUrl(null);
      setFeedbackMessage(response.status === "confirmed" ? null : MSG_QR_READY);
      void pollAuthStatus();
    } catch (error) {
      setWarningMessage(
        error instanceof Error
          ? `${MSG_CHECK_LOGIN_ERROR} ${error.message}`
          : MSG_CHECK_LOGIN_ERROR,
      );
    } finally {
      setIsStartingSession(false);
    }
  }, [endSession, hasConfirmedSession, pollAuthStatus, startSession, userId]);

  const summary = useMemo<ZaloCrawlerSummary>(() => {
    const total = jobs.length;
    const queued = jobs.filter((job) => job.status === "queued").length;
    const running = jobs.filter((job) => job.status === "running").length;
    const completed = jobs.filter((job) => job.status === "completed").length;
    const failed = jobs.filter((job) => job.status === "failed").length;
    const totalMessages = jobs.reduce(
      (sum, job) => sum + job.progress.messages_collected,
      0,
    );
    const totalImages = jobs.reduce(
      (sum, job) => sum + job.progress.images_found,
      0,
    );
    const overallProgressPercent =
      total === 0 ? 0 : Math.round(((completed + failed) / total) * 100);

    return {
      total,
      queued,
      running,
      completed,
      failed,
      totalMessages,
      totalImages,
      overallProgressPercent,
    };
  }, [jobs]);

  return {
    userId,
    selectedWorkerId,
    workers,
    accounts,
    isLoadingWorkers,
    isLoadingAccounts,
    workersError,
    accountsError,
    sessionId,
    authStatus,
    isCheckingLoginStatus,
    isStartingSession,
    isOpeningManualScreen,
    isSubmittingGroups,
    isVerifyingGroups,
    isResumingSession,
    isEndingSession,
    feedbackMessage,
    errorMessage,
    warningMessage,
    loginUrl,
    manualViewerUrl,
    qrBase64,
    qrImageUrl,
    isLoggedIn,
    canCrawl,
    sessionExpired,
    crawledGroups,
    crawledGroupsSheetUrl,
    crawledGroupsTotal,
    isLoadingCrawledGroups,
    crawledGroupsError,
    groupRows,
    jobs,
    summary,
    canLaunchJobs:
      canCrawl &&
      sanitizeRows(groupRows).some((row) => row.verifyStatus === "verified") &&
      !isStartingSession &&
      !isOpeningManualScreen &&
      !isSubmittingGroups &&
      !isVerifyingGroups &&
      !isEndingSession &&
      activeJobIds.length === 0,
    hasConfirmedSession,
    maxMessagesPerGroup,
    setMaxMessagesPerGroup,
    switchWorker,
    switchAccount,
    refreshLoginStatus: pollAuthStatus,
    createAccount,
    deleteAccount,
    updateAccount,
    startSession,
    openManualScreen,
    resumeManualLogin,
    addGroupRow,
    addCrawledGroup,
    updateGroupRow,
    removeGroupRow,
    verifyGroupRows,
    startCrawlForGroups,
    retryGroup,
    endSession,
    restartSession,
  };
}
