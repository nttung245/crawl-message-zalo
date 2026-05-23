"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { API_BASE_URL } from "@/lib/env";
import {
  deleteAllZaloSessions,
  deleteZaloSession,
  getZaloCrawledGroups,
  getZaloCurrentStatus,
  resumeZaloManualLogin,
  startZaloManualLogin,
  getZaloJobs,
  startZaloCrawl,
} from "@/services/zaloCrawlerService";
import type {
  ZaloAuthStatus,
  ZaloCrawledGroupItem,
  ZaloCrawledGroupsResponse,
  ZaloCurrentStatusResponse,
  ZaloJobData,
  ZaloJobProgress,
  ZaloJobStatus,
  ZaloMessage,
} from "@/types/zalo-api";

const AUTH_POLL_INTERVAL_MS = 2000;
const JOB_POLL_INTERVAL_MS = 2500;
const JOB_STALL_TIMEOUT_MS = 45000;
const RESUME_RETRY_ATTEMPTS = 20;
const RESUME_RETRY_INTERVAL_MS = 2000;
const DEFAULT_ZALO_USER_ID = "default";
const INITIAL_GROUP_ROW_ID = "zalo-group-0";

const MSG_LOAD_CRAWLED_GROUPS_ERROR = "Kh\u00f4ng th\u1ec3 t\u1ea3i danh s\u00e1ch nh\u00f3m \u0111\u00e3 crawl.";
const MSG_CHECK_LOGIN_ERROR = "Kh\u00f4ng th\u1ec3 ki\u1ec3m tra tr\u1ea1ng th\u00e1i \u0111\u0103ng nh\u1eadp Zalo.";
const MSG_UPDATE_PROGRESS_ERROR = "Kh\u00f4ng th\u1ec3 c\u1eadp nh\u1eadt ti\u1ebfn \u0111\u1ed9 crawl Zalo.";
const MSG_MANUAL_OPENED =
  "\u0110\u00e3 m\u1edf m\u00e0n h\u00ecnh Zalo remote. H\u00e3y \u0111\u0103ng nh\u1eadp/x\u1eed l\u00fd \u0111\u1ed3ng b\u1ed9 r\u1ed3i b\u1ea5m 'Ti\u1ebfp t\u1ee5c crawl'.";
const MSG_MANUAL_RESUME_WAITING =
  "Phi\u00ean Zalo ch\u01b0a s\u1eb5n s\u00e0ng crawl. H\u00e3y ho\u00e0n t\u1ea5t thao t\u00e1c trong m\u00e0n h\u00ecnh remote r\u1ed3i th\u1eed l\u1ea1i.";
const MSG_GROUP_ADDED = "\u0110\u00e3 th\u00eam nh\u00f3m v\u00e0o danh s\u00e1ch crawl.";
const MSG_GROUP_EXISTS = "Nh\u00f3m n\u00e0y \u0111\u00e3 c\u00f3 trong danh s\u00e1ch crawl.";
const MSG_LOGIN_REQUIRED =
  "C\u1ea7n ho\u00e0n t\u1ea5t \u0111\u0103ng nh\u1eadp Zalo tr\u01b0\u1edbc khi ch\u1ea1y crawl.";
const MSG_GROUP_REQUIRED =
  "Th\u00eam \u00edt nh\u1ea5t m\u1ed9t t\u00ean nh\u00f3m Zalo tr\u01b0\u1edbc khi ch\u1ea1y crawl.";
const MSG_JOB_INIT_ERROR = "Kh\u00f4ng th\u1ec3 kh\u1edfi t\u1ea1o job crawl.";
const MSG_ALL_JOB_INIT_ERROR =
  "Kh\u00f4ng th\u1ec3 t\u1ea1o job crawl n\u00e0o. Ki\u1ec3m tra l\u1ed7i chi ti\u1ebft theo t\u1eebng nh\u00f3m.";
const MSG_SESSION_ENDED = "\u0110\u00e3 k\u1ebft th\u00fac phi\u00ean Zalo.";
const MSG_CLOSE_SESSION_ERROR = "Kh\u00f4ng th\u1ec3 \u0111\u00f3ng phi\u00ean Zalo tr\u00ean server.";

export interface ZaloGroupInputRow {
  id: string;
  groupName: string;
  sheetTab: string;
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
  sessionId: string | null;
  authStatus: ZaloAuthStatus;
  isCheckingLoginStatus: boolean;
  isSubmittingGroups: boolean;
  isResumingSession: boolean;
  isEndingSession: boolean;
  feedbackMessage: string | null;
  errorMessage: string | null;
  warningMessage: string | null;
  loginUrl: string | null;
  manualViewerUrl: string | null;
  isLoggedIn: boolean;
  canCrawl: boolean;
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
  startCrawlForGroups: () => Promise<void>;
  retryGroup: (rowId: string) => Promise<void>;
  endSession: () => Promise<void>;
}

function createGroupRow(seed = 0): ZaloGroupInputRow {
  return {
    id: seed === 0 ? INITIAL_GROUP_ROW_ID : `zalo-group-${seed}`,
    groupName: "",
    sheetTab: "",
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
  response: { job_id: string; sheet_url: string; status?: "queued" | "running" },
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
  if (payload.status === "confirmed" && payload.can_crawl) return "confirmed";
  if (payload.status === "waiting_scan") return "waiting_scan";
  if (payload.status === "qr_expired") return "qr_expired";
  return "not_logged_in";
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export function useZaloCrawlerFlow(): ZaloCrawlerFlowValue {
  const userId = DEFAULT_ZALO_USER_ID;
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [authStatus, setAuthStatus] = useState<ZaloAuthStatus>("not_logged_in");
  const [isCheckingLoginStatus, setIsCheckingLoginStatus] = useState(true);
  const [isSubmittingGroups, setIsSubmittingGroups] = useState(false);
  const [isResumingSession, setIsResumingSession] = useState(false);
  const [isEndingSession, setIsEndingSession] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [warningMessage, setWarningMessage] = useState<string | null>(null);
  const [loginUrl, setLoginUrl] = useState<string | null>(null);
  const [manualViewerUrl, setManualViewerUrl] = useState<string | null>(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [canCrawl, setCanCrawl] = useState(false);
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

  const authIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const jobIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const authEventSourceRef = useRef<EventSource | null>(null);
  const manualViewerWindowRef = useRef<Window | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const activeJobIdsRef = useRef<string[]>([]);

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

  useEffect(() => {
    return () => {
      clearAuthPolling();
      clearJobPolling();
      clearAuthEventStream();
    };
  }, [clearAuthEventStream, clearAuthPolling, clearJobPolling]);

  const loadCrawledGroups = useCallback(async () => {
    setIsLoadingCrawledGroups(true);
    setCrawledGroupsError(null);

    try {
      const response: ZaloCrawledGroupsResponse = await getZaloCrawledGroups();
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
  }, []);

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
  }, []);

  const applyAuthStatus = useCallback((statusResponse: ZaloCurrentStatusResponse) => {
    setSessionId(statusResponse.session_id);
    setLoginUrl(statusResponse.login_url);
    setManualViewerUrl(statusResponse.manual_viewer_url ?? null);
    setIsLoggedIn(statusResponse.is_logged_in);
    setCanCrawl(statusResponse.can_crawl);
    setAuthStatus(mapCurrentStatusToAuthStatus(statusResponse));
    setWarningMessage(null);
  }, []);

  const pollAuthStatus = useCallback(async () => {
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
  }, [applyAuthStatus, userId]);

  useEffect(() => {
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
  }, [clearAuthPolling, pollAuthStatus]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }

    clearAuthEventStream();
    const streamUrl = `${API_BASE_URL}/api/zalo/auth/events?user_id=${encodeURIComponent(userId)}`;
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
  }, [applyAuthStatus, clearAuthEventStream, userId]);

  const pollRunningJobs = useCallback(async () => {
    const activeJobIds = activeJobIdsRef.current;
    if (activeJobIds.length === 0) return;

    try {
      const jobs = await getZaloJobs();
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
    activeJobIdsRef.current = activeJobIds;
    clearJobPolling();

    if (activeJobIds.length === 0) return;

    jobIntervalRef.current = setInterval(() => {
      void pollRunningJobs();
    }, JOB_POLL_INTERVAL_MS);

    return clearJobPolling;
  }, [activeJobIds, clearJobPolling, pollRunningJobs]);

  const openManualScreen = useCallback(async () => {
    setErrorMessage(null);
    setWarningMessage(null);
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
    }
  }, [manualViewerUrl, pollAuthStatus, userId]);

  const startSession = useCallback(async () => {
    await openManualScreen();
  }, [openManualScreen]);

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
            "Phi\u00ean Zalo \u0111\u00e3 s\u1eb5n s\u00e0ng. B\u1ea1n c\u00f3 th\u1ec3 ch\u1ea1y crawl.",
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
          id: `zalo-group-${nextSeed}-${crypto.randomUUID()}`,
          groupName: "",
          sheetTab: "",
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
              }
            : row,
        );
      }

      return [
        ...previous,
        {
          id: `zalo-group-${previous.length}-${crypto.randomUUID()}`,
          groupName,
          sheetTab,
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
          row.id === rowId ? { ...row, [field]: value } : row,
        ),
      );
    },
    [],
  );

  const removeGroupRow = useCallback((rowId: string) => {
    setGroupRows((previous) => {
      if (previous.length <= 1) {
        return previous.map((row) =>
          row.id === rowId ? { ...row, groupName: "", sheetTab: "" } : row,
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
  }, []);

  const launchRows = useCallback(
    async (rows: ZaloGroupInputRow[]) => {
      const currentSessionId = sessionIdRef.current;
      if (!canCrawl) {
        setErrorMessage(MSG_LOGIN_REQUIRED);
        return;
      }

      const cleanedRows = sanitizeRows(rows);
      if (cleanedRows.length === 0) {
        setErrorMessage(MSG_GROUP_REQUIRED);
        return;
      }

      const duplicateNames = new Set<string>();
      const seenNames = new Set<string>();
      for (const row of cleanedRows) {
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

      const results = await Promise.all(
        cleanedRows.map(async (row) => {
          try {
            const response = await startZaloCrawl({
              sessionId: currentSessionId,
              userId,
              group_name: row.groupName,
              sheet_tab: row.sheetTab || row.groupName,
            });
            return { ok: true as const, row, response };
          } catch (error) {
            return {
              ok: false as const,
              row,
              message: error instanceof Error ? error.message : MSG_JOB_INIT_ERROR,
            };
          }
        }),
      );

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
    [canCrawl, userId],
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
      const currentSessionId = sessionIdRef.current;
      if (currentSessionId) {
        await deleteZaloSession(currentSessionId);
      }
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
    sessionId,
    authStatus,
    isCheckingLoginStatus,
    isSubmittingGroups,
    isResumingSession,
    isEndingSession,
    feedbackMessage,
    errorMessage,
    warningMessage,
    loginUrl,
    manualViewerUrl,
    isLoggedIn,
    canCrawl,
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
      sanitizeRows(groupRows).length > 0 &&
      !isSubmittingGroups &&
      !isEndingSession,
    hasConfirmedSession: canCrawl && Boolean(sessionId),
    startSession,
    openManualScreen,
    resumeManualLogin,
    addGroupRow,
    addCrawledGroup,
    updateGroupRow,
    removeGroupRow,
    startCrawlForGroups,
    retryGroup,
    endSession,
  };
}
