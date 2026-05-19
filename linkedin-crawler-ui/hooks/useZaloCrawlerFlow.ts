"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  deleteZaloSession,
  getZaloAuthStatus,
  getZaloJobs,
  initZaloAuthSession,
  refreshZaloQr,
  startZaloCrawl,
} from "@/services/zaloCrawlerService";
import type {
  ZaloAuthStatus,
  ZaloJobData,
  ZaloJobProgress,
  ZaloJobStatus,
  ZaloMessage,
} from "@/types/zalo-api";

const AUTH_POLL_INTERVAL_MS = 2000;
const JOB_POLL_INTERVAL_MS = 2500;
const JOB_STALL_TIMEOUT_MS = 45000;
const INITIAL_GROUP_ROW_ID = "zalo-group-0";

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
  sessionId: string | null;
  qrBase64: string | null;
  authStatus: ZaloAuthStatus | null;
  qrExpiresAt: number | null;
  isQrModalOpen: boolean;
  isInitializingSession: boolean;
  isRefreshingQr: boolean;
  isSubmittingGroups: boolean;
  feedbackMessage: string | null;
  errorMessage: string | null;
  warningMessage: string | null;
  groupRows: ZaloGroupInputRow[];
  jobs: ZaloTrackedJobState[];
  summary: ZaloCrawlerSummary;
  canLaunchJobs: boolean;
  hasConfirmedSession: boolean;
  startSession: () => Promise<void>;
  closeQrModal: () => Promise<void>;
  refreshQrCode: () => Promise<void>;
  addGroupRow: () => void;
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

function buildJobSignature(job: Pick<ZaloTrackedJobState, "status" | "progress" | "sheetUrl" | "completedAt" | "error" | "messages">): string {
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

function makeRunningJob(
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
    stalled: isActiveJobStatus(nextBase.status) && now - lastChangedAt >= JOB_STALL_TIMEOUT_MS,
  };
}

export function useZaloCrawlerFlow(): ZaloCrawlerFlowValue {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [qrBase64, setQrBase64] = useState<string | null>(null);
  const [authStatus, setAuthStatus] = useState<ZaloAuthStatus | null>(null);
  const [qrExpiresAt, setQrExpiresAt] = useState<number | null>(null);
  const [isQrModalOpen, setIsQrModalOpen] = useState(false);
  const [isInitializingSession, setIsInitializingSession] = useState(false);
  const [isRefreshingQr, setIsRefreshingQr] = useState(false);
  const [isSubmittingGroups, setIsSubmittingGroups] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [warningMessage, setWarningMessage] = useState<string | null>(null);
  const [groupRows, setGroupRows] = useState<ZaloGroupInputRow[]>(() => [
    createGroupRow(0),
  ]);
  const [jobsByRow, setJobsByRow] = useState<Record<string, ZaloTrackedJobState>>(
    {},
  );

  const authIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const jobIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
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

  useEffect(() => {
    return () => {
      clearAuthPolling();
      clearJobPolling();
    };
  }, [clearAuthPolling, clearJobPolling]);

  const resetAuthState = useCallback(() => {
    setSessionId(null);
    setQrBase64(null);
    setAuthStatus(null);
    setQrExpiresAt(null);
    setIsQrModalOpen(false);
  }, []);

  const pollAuthStatus = useCallback(async () => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId) return;

    try {
      const statusResponse = await getZaloAuthStatus(currentSessionId);
      setAuthStatus((previous) =>
        previous === statusResponse.status ? previous : statusResponse.status,
      );
      setWarningMessage(null);

      if (statusResponse.status === "confirmed") {
        clearAuthPolling();
        setIsQrModalOpen(false);
        setFeedbackMessage("Đăng nhập Zalo đã được xác nhận. Có thể thêm nhóm và chạy crawl.");
      }

      if (statusResponse.status === "qr_expired") {
        clearAuthPolling();
        setWarningMessage("Mã QR đã hết hạn. Làm mới QR để tiếp tục đăng nhập.");
      }
    } catch (error) {
      setWarningMessage(
        error instanceof Error
          ? `Không thể kiểm tra trạng thái đăng nhập: ${error.message}`
          : "Không thể kiểm tra trạng thái đăng nhập Zalo.",
      );
    }
  }, [clearAuthPolling]);

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
            const stalled =
              now - jobState.lastChangedAt >= JOB_STALL_TIMEOUT_MS;
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
          ? `Không thể cập nhật tiến độ crawl: ${error.message}`
          : "Không thể cập nhật tiến độ crawl Zalo.",
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

  const startSession = useCallback(async () => {
    clearAuthPolling();
    setIsInitializingSession(true);
    setErrorMessage(null);
    setWarningMessage(null);
    setFeedbackMessage(null);

    try {
      const response = await initZaloAuthSession();
      setSessionId(response.session_id);
      setQrBase64(response.qr_base64);
      setAuthStatus(response.status);
      setQrExpiresAt(Date.now() + response.expires_in * 1000);
      setIsQrModalOpen(true);
      setFeedbackMessage("Đã tạo phiên đăng nhập. Quét mã QR bằng Zalo để tiếp tục.");

      authIntervalRef.current = setInterval(() => {
        void pollAuthStatus();
      }, AUTH_POLL_INTERVAL_MS);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Không thể khởi tạo phiên đăng nhập Zalo.",
      );
    } finally {
      setIsInitializingSession(false);
    }
  }, [clearAuthPolling, pollAuthStatus]);

  const closeQrModal = useCallback(async () => {
    setIsQrModalOpen(false);

    if (authStatus === "confirmed") {
      return;
    }

    clearAuthPolling();
    const currentSessionId = sessionIdRef.current;
    resetAuthState();

    if (!currentSessionId) return;

    try {
      await deleteZaloSession(currentSessionId);
      setFeedbackMessage("Đã hủy phiên đăng nhập Zalo.");
    } catch {
      /* ignore cleanup failures */
    }
  }, [authStatus, clearAuthPolling, resetAuthState]);

  const refreshQrCode = useCallback(async () => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId) return;

    setIsRefreshingQr(true);
    setErrorMessage(null);

    try {
      const response = await refreshZaloQr(currentSessionId);
      setQrBase64((previous) =>
        previous === response.qr_base64 ? previous : response.qr_base64,
      );
      setAuthStatus(response.status);
      setQrExpiresAt(Date.now() + 2 * 60 * 1000);
      setWarningMessage(null);
      setFeedbackMessage("Đã làm mới mã QR Zalo.");

      if (!authIntervalRef.current) {
        authIntervalRef.current = setInterval(() => {
          void pollAuthStatus();
        }, AUTH_POLL_INTERVAL_MS);
      }
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Không thể làm mới mã QR Zalo.",
      );
    } finally {
      setIsRefreshingQr(false);
    }
  }, [pollAuthStatus]);

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

  const launchRows = useCallback(async (rows: ZaloGroupInputRow[]) => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId || authStatus !== "confirmed") {
      setErrorMessage("Cần hoàn tất đăng nhập Zalo trước khi chạy crawl.");
      return;
    }

    const cleanedRows = sanitizeRows(rows);
    if (cleanedRows.length === 0) {
      setErrorMessage("Thêm ít nhất một tên nhóm Zalo trước khi chạy crawl.");
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
        `Tên nhóm bị trùng: ${Array.from(duplicateNames).join(", ")}.`,
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
            group_name: row.groupName,
            sheet_tab: row.sheetTab || row.groupName,
          });
          return { ok: true as const, row, response };
        } catch (error) {
          return {
            ok: false as const,
            row,
            message:
              error instanceof Error
                ? error.message
                : "Không thể khởi tạo job crawl.",
          };
        }
      }),
    );

    setJobsByRow((previous) => {
      const next = { ...previous };
      for (const result of results) {
        next[result.row.id] = result.ok
          ? makeRunningJob(result.row, result.response)
          : makeLocalFailedJob(result.row, result.message);
      }
      return next;
    });

    const succeededCount = results.filter((result) => result.ok).length;
    const failedCount = results.length - succeededCount;

    if (succeededCount > 0) {
      setFeedbackMessage(
        `Đã tạo ${succeededCount} job crawl Zalo${failedCount > 0 ? `, ${failedCount} job lỗi khởi tạo` : ""}.`,
      );
    } else {
      setErrorMessage("Không thể tạo job crawl nào. Kiểm tra lỗi chi tiết theo từng nhóm.");
    }

    setIsSubmittingGroups(false);
  }, [authStatus]);

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
    clearAuthPolling();
    const currentSessionId = sessionIdRef.current;
    resetAuthState();

    if (!currentSessionId) return;

    try {
      await deleteZaloSession(currentSessionId);
      setFeedbackMessage("Đã kết thúc phiên đăng nhập Zalo.");
    } catch (error) {
      setWarningMessage(
        error instanceof Error
          ? `Không thể đóng phiên Zalo trên server: ${error.message}`
          : "Không thể đóng phiên Zalo trên server.",
      );
    }
  }, [clearAuthPolling, resetAuthState]);

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
    sessionId,
    qrBase64,
    authStatus,
    qrExpiresAt,
    isQrModalOpen,
    isInitializingSession,
    isRefreshingQr,
    isSubmittingGroups,
    feedbackMessage,
    errorMessage,
    warningMessage,
    groupRows,
    jobs,
    summary,
    canLaunchJobs:
      authStatus === "confirmed" &&
      sanitizeRows(groupRows).length > 0 &&
      !isSubmittingGroups,
    hasConfirmedSession: authStatus === "confirmed" && Boolean(sessionId),
    startSession,
    closeQrModal,
    refreshQrCode,
    addGroupRow,
    updateGroupRow,
    removeGroupRow,
    startCrawlForGroups,
    retryGroup,
    endSession,
  };
}
