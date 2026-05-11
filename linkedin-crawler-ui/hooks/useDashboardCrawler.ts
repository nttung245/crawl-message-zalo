"use client";

import { useCallback, useEffect, useId, useMemo, useState } from "react";

import type {
  CrawlResultRow,
  CrawlTableViewMode,
} from "@/components/features/dashboard/types";
import { DASHBOARD_PAGE_SIZE } from "@/components/features/dashboard/constants";
import {
  crawlLinkedInGroup,
  ensureProfileSlugIfMissing,
  filterLinkedInPosts,
  getAllLinkedInPosts,
  loginLinkedIn,
  startN8nWorkflow,
} from "@/services/linkedinCrawlerService";
import { parseYmd, todayYmd, yesterdayYmd } from "@/lib/date-helpers";
import type {
  CrawlDataResponse,
  CrawlSessionGroup,
  FilterDataRequest,
} from "@/types/api";
import { writeLinkedInCredentials } from "@/lib/credentials";

const LINKEDIN_GROUP_URL_PATTERN =
  /^https:\/\/(www\.)?linkedin\.com\/groups\/\d+\/?/i;

function countPostsInSessions(sessions: CrawlSessionGroup[] | null): number {
  if (!sessions?.length) return 0;
  return sessions.reduce(
    (acc, s) => acc + (Array.isArray(s.posts) ? s.posts.length : 0),
    0,
  );
}

export interface DashboardCrawlerValue {
  emailId: string;
  passwordId: string;
  maxPostsId: string;
  targetDateId: string;
  modeId: string;
  delayId: string;
  urlsId: string;
  email: string;
  setEmail: (v: string) => void;
  password: string;
  setPassword: (v: string) => void;
  maxPosts: number;
  setMaxPosts: (v: number) => void;
  targetDate: string;
  setTargetDate: (v: string) => void;
  mode: "Detailed" | "Fast";
  setMode: (v: "Detailed" | "Fast") => void;
  delaySec: number;
  setDelaySec: (v: number) => void;
  groupUrls: string;
  setGroupUrls: (v: string) => void;
  isCrawling: boolean;
  feedbackMessage: string | null;
  errorMessage: string | null;
  filterDate: string;
  setFilterDate: (v: string) => void;
  filterDateFrom: string;
  setFilterDateFrom: (v: string) => void;
  filterDateTo: string;
  setFilterDateTo: (v: string) => void;
  isFiltering: boolean;
  filterResult: CrawlSessionGroup[] | null;
  filterMessage: string | null;
  filterError: string | null;
  isGettingAllPosts: boolean;
  allPostsResult: CrawlSessionGroup[] | null;
  /** Tổng bài trong dataset get-all-posts (không phụ thuộc chế độ bảng). */
  allPostsCount: number;
  crawlTableViewMode: CrawlTableViewMode;
  /** Hàng hiển thị trong bảng Kết quả Crawl (theo chế độ all | filtered). */
  crawlSessionsForTable: CrawlSessionGroup[] | null;
  crawlSessionsTableBusy: boolean;
  displayedCrawlSessionCount: number;
  displayedCrawlPostCount: number;
  /** Nhãn cột / stats khi đang xem sau filter (ngày chọn hoặc không chọn). */
  filterAppliedLabel: string;
  showAllCrawlSessions: () => void;
  /** Xóa điều kiện lọc, làm mới danh sách đầy đủ từ /get-all-posts. */
  handleClearCrawlFilter: () => void;
  allPostsMessage: string | null;
  allPostsError: string | null;
  totalResultCount: number;
  totalPages: number;
  safePage: number;
  pageStart: number;
  pageEnd: number;
  paginatedRows: CrawlResultRow[];
  bentoStats: { members: string; velocity: string; accuracy: string };
  handleResetForm: () => void;
  handleValidateLinks: () => void;
  handleStartCrawl: () => Promise<void>;
  applyAccountCredentials: (
    nextEmail: string,
    nextPassword: string,
    linkedInSessionId?: string | null,
  ) => Promise<void>;
  refreshDashboardData: () => Promise<void>;
  dashboardReloadToken: number;
  crawlSuccessModalOpen: boolean;
  crawlSuccessModalMessage: string | null;
  closeCrawlSuccessModal: () => void;
  confirmCrawlSuccessModal: () => Promise<void>;
  handleFilterToday: () => void;
  handleFilterYesterday: () => void;
  handleFilterLast7Days: () => void;
  handleFilterLast30Days: () => void;
  handleFilterDateRange: () => void;
  handleFilterSingleDate: () => void;
  handleGetAllPosts: () => void;
  handleGoPrevPage: () => void;
  handleGoNextPage: () => void;
  handleRetryRow: (id: string) => Promise<void>;
  parsedGroupLines: string[];
  isGroupIndexSelected: (globalIndex: number) => boolean;
  toggleGroupSelection: (index: number) => void;
  toggleSelectAllGroupsOnPage: () => void;
  groupsTotalCount: number;
  groupsTotalPages: number;
  groupsSafePage: number;
  groupsPageStart: number;
  groupsPageEnd: number;
  paginatedGroupRows: { globalIndex: number; url: string }[];
  handleGroupsGoPrevPage: () => void;
  handleGroupsGoNextPage: () => void;
}

export function useDashboardCrawler(): DashboardCrawlerValue {
  const emailId = useId();
  const passwordId = useId();
  const maxPostsId = useId();
  const targetDateId = useId();
  const modeId = useId();
  const delayId = useId();
  const urlsId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [maxPosts, setMaxPosts] = useState(100);
  const [targetDate, setTargetDate] = useState("");
  const [mode, setMode] = useState<"Detailed" | "Fast">("Detailed");
  const [delaySec, setDelaySec] = useState(5);
  const [groupUrls, setGroupUrls] = useState("");
  const [isCrawling, setIsCrawling] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [filterDate, setFilterDate] = useState("");
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");
  const [isFiltering, setIsFiltering] = useState(false);
  const [filterResult, setFilterResult] = useState<CrawlSessionGroup[] | null>(
    null,
  );
  const [filterMessage, setFilterMessage] = useState<string | null>(null);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [isGettingAllPosts, setIsGettingAllPosts] = useState(false);
  const [allPostsResult, setAllPostsResult] = useState<CrawlSessionGroup[] | null>(
    null,
  );
  const [crawlTableViewMode, setCrawlTableViewMode] =
    useState<CrawlTableViewMode>("all");
  const [allPostsMessage, setAllPostsMessage] = useState<string | null>(null);
  const [allPostsError, setAllPostsError] = useState<string | null>(null);
  const [filterAppliedLabel, setFilterAppliedLabel] = useState("");
  const [dashboardReloadToken, setDashboardReloadToken] = useState(0);
  const [crawlSuccessModalOpen, setCrawlSuccessModalOpen] = useState(false);
  const [crawlSuccessModalMessage, setCrawlSuccessModalMessage] = useState<
    string | null
  >(null);

  const [results, setResults] = useState<CrawlResultRow[]>([]);
  const [page, setPage] = useState(1);
  const [groupPage, setGroupPage] = useState(1);
  /** Chỉ số dòng bị bỏ tick (mặc định mọi dòng đều được chọn). */
  const [deselectedGroupIndices, setDeselectedGroupIndices] = useState<
    Set<number>
  >(() => new Set());

  const parsedGroupLines = useMemo(
    () =>
      groupUrls
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean),
    [groupUrls],
  );

  const groupsTotalCount = parsedGroupLines.length;
  const groupsTotalPages = Math.max(
    1,
    Math.ceil(groupsTotalCount / DASHBOARD_PAGE_SIZE),
  );
  const groupsSafePage = Math.min(groupPage, groupsTotalPages);
  const groupsPageStart =
    groupsTotalCount === 0 ? 0 : (groupsSafePage - 1) * DASHBOARD_PAGE_SIZE + 1;
  const groupsPageEnd = Math.min(
    groupsSafePage * DASHBOARD_PAGE_SIZE,
    groupsTotalCount,
  );

  const paginatedGroupRows = useMemo(() => {
    const start = (groupsSafePage - 1) * DASHBOARD_PAGE_SIZE;
    return parsedGroupLines
      .slice(start, start + DASHBOARD_PAGE_SIZE)
      .map((url, sliceIdx) => ({
        globalIndex: start + sliceIdx,
        url,
      }));
  }, [parsedGroupLines, groupsSafePage]);

  const isGroupIndexSelected = useCallback(
    (globalIndex: number) => !deselectedGroupIndices.has(globalIndex),
    [deselectedGroupIndices],
  );

  const toggleGroupSelection = useCallback(
    (index: number) => {
      if (index < 0 || index >= parsedGroupLines.length) return;
      setDeselectedGroupIndices((prev) => {
        const next = new Set(prev);
        if (next.has(index)) {
          next.delete(index);
        } else {
          next.add(index);
        }
        return next;
      });
    },
    [parsedGroupLines.length],
  );

  const toggleSelectAllGroupsOnPage = useCallback(() => {
    const start = (groupsSafePage - 1) * DASHBOARD_PAGE_SIZE;
    const pageSlice = parsedGroupLines.slice(
      start,
      start + DASHBOARD_PAGE_SIZE,
    );
    const indices = pageSlice.map((_, i) => start + i);
    if (indices.length === 0) return;
    setDeselectedGroupIndices((prev) => {
      const next = new Set(prev);
      const allSelected = indices.every((i) => !next.has(i));
      if (allSelected) {
        for (const i of indices) {
          next.add(i);
        }
      } else {
        for (const i of indices) {
          next.delete(i);
        }
      }
      return next;
    });
  }, [groupsSafePage, parsedGroupLines]);

  const handleGroupsGoPrevPage = useCallback(() => {
    setGroupPage((p) => Math.max(1, p - 1));
  }, []);

  const handleGroupsGoNextPage = useCallback(() => {
    setGroupPage((p) => Math.min(groupsTotalPages, p + 1));
  }, [groupsTotalPages]);

  const totalResultCount = results.length;
  const totalPages = Math.max(
    1,
    Math.ceil(totalResultCount / DASHBOARD_PAGE_SIZE),
  );
  const safePage = Math.min(page, totalPages);
  const pageStart =
    totalResultCount === 0 ? 0 : (safePage - 1) * DASHBOARD_PAGE_SIZE + 1;
  const pageEnd = Math.min(safePage * DASHBOARD_PAGE_SIZE, totalResultCount);

  const paginatedRows = useMemo(() => {
    const start = (safePage - 1) * DASHBOARD_PAGE_SIZE;
    return results.slice(start, start + DASHBOARD_PAGE_SIZE);
  }, [results, safePage]);

  const bentoStats = useMemo(() => {
    const completedRows = results.filter((r) => r.status === "Completed");
    const completedPosts = completedRows.reduce((sum, r) => sum + r.posts, 0);
    return {
      members: results.length.toLocaleString("vi-VN"),
      velocity: `${completedPosts.toLocaleString("vi-VN")} bài viết`,
      accuracy: `${completedRows.length}/${results.length || 0} nhóm hoàn tất`,
    };
  }, [results]);

  const handleResetForm = useCallback(() => {
    setEmail("");
    setPassword("");
    setMaxPosts(100);
    setTargetDate("");
    setMode("Detailed");
    setDelaySec(5);
    setGroupUrls("");
    setDeselectedGroupIndices(new Set());
    setFeedbackMessage(null);
    setErrorMessage(null);
    setFilterDate("");
    setFilterDateFrom("");
    setFilterDateTo("");
    setFilterAppliedLabel("");
    setFilterResult(null);
    setFilterMessage(null);
    setFilterError(null);
    setAllPostsResult(null);
    setAllPostsMessage(null);
    setAllPostsError(null);
  }, []);

  const parsedGroupUrls = useCallback(
    () =>
      groupUrls
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean),
    [groupUrls],
  );

  const handleValidateLinks = useCallback(() => {
    const lines = parsedGroupUrls();
    if (lines.length === 0) {
      setFeedbackMessage(null);
      setErrorMessage("Vui lòng nhập ít nhất một URL nhóm LinkedIn.");
      return;
    }
    const invalidCount = lines.filter(
      (line) => !LINKEDIN_GROUP_URL_PATTERN.test(line),
    ).length;
    setErrorMessage(
      invalidCount > 0
        ? `${invalidCount} URL nhóm LinkedIn chưa hợp lệ.`
        : null,
    );
    setFeedbackMessage(
      invalidCount === 0
        ? `Đã kiểm tra ${lines.length} URL nhóm LinkedIn hợp lệ.`
        : null,
    );
  }, [parsedGroupUrls]);

  const handleStartCrawl = useCallback(async () => {
    const lines = parsedGroupUrls();
    const invalidCount = lines.filter(
      (line) => !LINKEDIN_GROUP_URL_PATTERN.test(line),
    ).length;

    setFeedbackMessage(null);
    setErrorMessage(null);

    if (!email.trim() || !password.trim()) {
      setErrorMessage("Vui lòng nhập email và mật khẩu LinkedIn.");
      return;
    }
    if (lines.length === 0) {
      setErrorMessage("Vui lòng chọn ít nhất một URL nhóm LinkedIn.");
      return;
    }
    if (invalidCount > 0) {
      setErrorMessage(`${invalidCount} URL nhóm LinkedIn chưa hợp lệ.`);
      return;
    }

    setIsCrawling(true);

    try {
      writeLinkedInCredentials(email.trim(), password.trim());
      const response = await startN8nWorkflow({
        email: email.trim(),
        password,
        force_relogin: true,
        max_posts: Math.max(1, Math.min(maxPosts, 500)),
        target_date: targetDate || undefined,
        mode,
        delay_sec: Math.max(0, delaySec),
        group_urls: lines,
      });

      if (!response.success) {
        throw new Error(response.message || "Không thể gọi API /start.");
      }
      const webhookMessage = extractStartWebhookMessage(response.data);
      const sessionText = response.data?.id_session_crawl
        ? `Session: ${response.data.id_session_crawl}`
        : null;
      const modalMessage = [webhookMessage, sessionText].filter(Boolean).join("\n");
      setCrawlSuccessModalMessage(modalMessage || "Cào dữ liệu thành công.");
      setCrawlSuccessModalOpen(true);
      setFeedbackMessage(
        response.message || `Đã gửi yêu cầu crawl ${lines.length} nhóm tới workflow start.`,
      );
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Không thể gọi API /start.",
      );
    } finally {
      setIsCrawling(false);
    }
  }, [
    parsedGroupUrls,
    email,
    password,
    targetDate,
    maxPosts,
    mode,
    delaySec,
  ]);

  const closeCrawlSuccessModal = useCallback(() => {
    setCrawlSuccessModalOpen(false);
  }, []);

  const loadN8nSessions = useCallback(
    async (options: {
      clear?: boolean;
      withSuccessMessage?: boolean;
      emailOverride?: string;
    } = {}) => {
      const e = (options.emailOverride ?? email).trim();
      if (!e) {
        setAllPostsError("Vui lòng nhập email LinkedIn.");
        return;
      }
      setAllPostsMessage(null);
      setAllPostsError(null);
      if (options.clear) {
        setAllPostsResult(null);
      }
      setIsGettingAllPosts(true);
      try {
        const response = await getAllLinkedInPosts({
          email: e,
          filters: {},
        });
        if (!response.success) {
          throw new Error(response.message || "Không thể lấy posts từ n8n.");
        }
        setAllPostsResult(response.data ?? []);
        setCrawlTableViewMode("all");
        if (options.withSuccessMessage) {
          setAllPostsMessage("Danh sách phiên cào đã được cập nhật");
        }
      } catch (error) {
        setAllPostsError(
          error instanceof Error ? error.message : "Lấy dữ liệu n8n thất bại.",
        );
      } finally {
        setIsGettingAllPosts(false);
      }
    },
    [email],
  );

  useEffect(() => {
    if (!email.trim()) return;
    void loadN8nSessions();
  }, [email, loadN8nSessions]);

  const runN8nDateFilter = useCallback(
    async (body: Omit<FilterDataRequest, "email">, summary: string) => {
      setFilterMessage(null);
      setFilterError(null);
      setFilterResult(null);
      setCrawlTableViewMode("filtered");

      const e = email.trim();
      if (!e) {
        setFilterError("Vui lòng nhập email LinkedIn trước khi filter.");
        setCrawlTableViewMode("all");
        return;
      }

      setIsFiltering(true);
      try {
        const response = await filterLinkedInPosts({
          email: e,
          ...body,
        });

        if (!response.success) {
          throw new Error(response.message || "Không thể filter dữ liệu.");
        }

        setFilterResult(response.data ?? []);
        setFilterMessage("Đã nhận dữ liệu filter từ n8n.");
        setFilterAppliedLabel(summary);
      } catch (error) {
        setCrawlTableViewMode("all");
        setFilterError(
          error instanceof Error ? error.message : "Filter dữ liệu thất bại.",
        );
      } finally {
        setIsFiltering(false);
      }
    },
    [email],
  );

  const handleFilterToday = useCallback(() => {
    const d = todayYmd();
    void runN8nDateFilter({ date: d }, `Một ngày: ${d} (hôm nay)`);
  }, [runN8nDateFilter]);

  const handleFilterYesterday = useCallback(() => {
    const d = yesterdayYmd();
    void runN8nDateFilter({ date: d }, `Một ngày: ${d} (hôm qua)`);
  }, [runN8nDateFilter]);

  const handleFilterLast7Days = useCallback(() => {
    void runN8nDateFilter(
      { preset: "last_7_days" },
      "Preset: 7 ngày gần nhất (last_7_days)",
    );
  }, [runN8nDateFilter]);

  const handleFilterLast30Days = useCallback(() => {
    void runN8nDateFilter(
      { preset: "last_30_days" },
      "Preset: 30 ngày gần nhất (last_30_days)",
    );
  }, [runN8nDateFilter]);

  const handleFilterDateRange = useCallback(() => {
    const from = filterDateFrom.trim();
    const to = filterDateTo.trim();
    if (!from && !to) {
      setFilterMessage(null);
      setFilterError("Nhập ít nhất «Từ ngày» hoặc «Đến ngày».");
      return;
    }
    const dFrom = from ? parseYmd(from) : null;
    const dTo = to ? parseYmd(to) : null;
    if ((from && !dFrom) || (to && !dTo)) {
      setFilterError("Định dạng ngày phải là YYYY-MM-DD.");
      return;
    }
    if (dFrom && dTo && dFrom.getTime() > dTo.getTime()) {
      setFilterError("Từ ngày phải trước hoặc bằng Đến ngày.");
      return;
    }
    const payload: Omit<FilterDataRequest, "email"> = {};
    if (from) payload.date_from = from;
    if (to) payload.date_to = to;
    const summary =
      from && to
        ? `Khoảng: ${from} → ${to}`
        : from
          ? `Từ ${from} (đến hôm nay — theo API)`
          : `Đến ${to} (một ngày — theo API)`;
    void runN8nDateFilter(payload, summary);
  }, [filterDateFrom, filterDateTo, runN8nDateFilter]);

  const handleFilterSingleDate = useCallback(() => {
    const d = filterDate.trim();
    if (!d) {
      setFilterMessage(null);
      setFilterError("Chọn một ngày để lọc.");
      return;
    }
    if (!parseYmd(d)) {
      setFilterError("Ngày không hợp lệ.");
      return;
    }
    void runN8nDateFilter({ date: d }, `Một ngày: ${d}`);
  }, [filterDate, runN8nDateFilter]);

  const handleGetAllPosts = useCallback(() => {
    void loadN8nSessions({ clear: true, withSuccessMessage: true });
  }, [loadN8nSessions]);

  const confirmCrawlSuccessModal = useCallback(async () => {
    setCrawlSuccessModalOpen(false);
    await loadN8nSessions({ clear: true, withSuccessMessage: true });
  }, [loadN8nSessions]);

  const refreshDashboardData = useCallback(async () => {
    await loadN8nSessions({ clear: true, withSuccessMessage: true });
    setDashboardReloadToken((v) => v + 1);
  }, [loadN8nSessions]);

  const applyAccountCredentials = useCallback(
    async (
      nextEmail: string,
      nextPassword: string,
      linkedInSessionId?: string | null,
    ) => {
      const normalizedEmail = nextEmail.trim();
      if (!normalizedEmail || !nextPassword.trim()) {
        setErrorMessage("Vui lòng nhập email và mật khẩu LinkedIn.");
        return;
      }
      setErrorMessage(null);
      setFeedbackMessage("Đang cập nhật tài khoản và làm mới dữ liệu...");
      setEmail(normalizedEmail);
      setPassword(nextPassword);
      writeLinkedInCredentials(normalizedEmail, nextPassword);
      await loadN8nSessions({
        clear: true,
        withSuccessMessage: true,
        emailOverride: normalizedEmail,
      });
      setDashboardReloadToken((v) => v + 1);

      let slugTail = "";
      try {
        const slugRes = await ensureProfileSlugIfMissing({
          email: normalizedEmail,
          sessionId: linkedInSessionId ?? undefined,
        });
        if (!slugRes.success) {
          slugTail = ` Đồng bộ profile slug chưa xong: ${slugRes.message || "lỗi không xác định"}.`;
        }
      } catch (slugErr) {
        slugTail = ` Đồng bộ profile slug chưa xong: ${slugErr instanceof Error ? slugErr.message : "lỗi mạng"}.`;
      }

      setFeedbackMessage(
        `Đã cập nhật tài khoản và làm mới dữ liệu mới nhất.${slugTail}`,
      );
    },
    [loadN8nSessions],
  );

  const showAllCrawlSessions = useCallback(() => {
    setCrawlTableViewMode("all");
  }, []);

  const handleClearCrawlFilter = useCallback(() => {
    setFilterResult(null);
    setFilterMessage(null);
    setFilterError(null);
    setFilterAppliedLabel("");
    setFilterDate("");
    setFilterDateFrom("");
    setFilterDateTo("");
    setCrawlTableViewMode("all");
    void loadN8nSessions({ clear: true, withSuccessMessage: true });
  }, [loadN8nSessions]);

  const crawlSessionsForTable = useMemo((): CrawlSessionGroup[] | null => {
    if (crawlTableViewMode === "filtered") {
      return filterResult;
    }
    return allPostsResult;
  }, [crawlTableViewMode, filterResult, allPostsResult]);

  const crawlSessionsTableBusy = useMemo(
    () =>
      (crawlTableViewMode === "all" && isGettingAllPosts) ||
      (crawlTableViewMode === "filtered" && isFiltering),
    [crawlTableViewMode, isGettingAllPosts, isFiltering],
  );

  const displayedCrawlSessionCount = crawlSessionsForTable?.length ?? 0;
  const displayedCrawlPostCount = useMemo(
    () => countPostsInSessions(crawlSessionsForTable),
    [crawlSessionsForTable],
  );

  const handleGoPrevPage = useCallback(() => {
    setPage((p) => Math.max(1, p - 1));
  }, []);

  const handleGoNextPage = useCallback(() => {
    setPage((p) => Math.min(totalPages, p + 1));
  }, [totalPages]);

  const handleRetryRow = useCallback(
    async (id: string) => {
      const targetRow = results.find((row) => row.id === id);
      const groupUrl = targetRow?.groupUrl;
      if (!groupUrl) return;

      if (!email.trim() || !password.trim()) {
        setErrorMessage("Vui lòng nhập email và mật khẩu LinkedIn để thử lại.");
        return;
      }

      setErrorMessage(null);
      setFeedbackMessage(null);
      setResults((rows) =>
        rows.map((row) =>
          row.id === id
            ? { ...row, status: "Processing" as const, posts: 0 }
            : row,
        ),
      );

      try {
        const loginResponse = await loginLinkedIn({
          email: email.trim(),
          password,
          forceRelogin: false,
        });
        if (loginResponse.need_otp || loginResponse.login_step === "need_otp") {
          throw new Error(
            "Tài khoản đang yêu cầu OTP. Vui lòng xác minh tại popup Tài khoản trước rồi thử lại.",
          );
        }
        if (!loginResponse.success || !loginResponse.session_id) {
          throw new Error(
            loginResponse.message || "Không thể lấy lại phiên LinkedIn.",
          );
        }

        const retryRow = await crawlOneGroup({
          groupUrl,
          sessionId: loginResponse.session_id,
          email: email.trim(),
          maxPosts,
          targetDate,
        });
        setResults((rows) =>
          rows.map((row) => (row.id === id ? retryRow : row)),
        );
        setFeedbackMessage(`Đã thử lại nhóm ${retryRow.groupName}.`);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Thử lại crawl thất bại.";
        setErrorMessage(message);
        setResults((rows) =>
          rows.map((row) =>
            row.id === id
              ? {
                  ...row,
                  status: "Failed" as const,
                  action: "retry" as const,
                  errorMessage: message,
                }
              : row,
          ),
        );
      }
    },
    [results, email, password, maxPosts, targetDate],
  );

  return {
    emailId,
    passwordId,
    maxPostsId,
    targetDateId,
    modeId,
    delayId,
    urlsId,
    email,
    setEmail,
    password,
    setPassword,
    maxPosts,
    setMaxPosts,
    targetDate,
    setTargetDate,
    mode,
    setMode,
    delaySec,
    setDelaySec,
    groupUrls,
    setGroupUrls,
    isCrawling,
    feedbackMessage,
    errorMessage,
    filterDate,
    setFilterDate,
    filterDateFrom,
    setFilterDateFrom,
    filterDateTo,
    setFilterDateTo,
    isFiltering,
    filterResult,
    filterMessage,
    filterError,
    isGettingAllPosts,
    allPostsResult,
    allPostsCount: countPostsInSessions(allPostsResult),
    crawlTableViewMode,
    crawlSessionsForTable,
    crawlSessionsTableBusy,
    displayedCrawlSessionCount,
    displayedCrawlPostCount,
    filterAppliedLabel,
    showAllCrawlSessions,
    handleClearCrawlFilter,
    allPostsMessage,
    allPostsError,
    totalResultCount,
    totalPages,
    safePage,
    pageStart,
    pageEnd,
    paginatedRows,
    bentoStats,
    handleResetForm,
    handleValidateLinks,
    handleStartCrawl,
    applyAccountCredentials,
    refreshDashboardData,
    dashboardReloadToken,
    crawlSuccessModalOpen,
    crawlSuccessModalMessage,
    closeCrawlSuccessModal,
    confirmCrawlSuccessModal,
    handleFilterToday,
    handleFilterYesterday,
    handleFilterLast7Days,
    handleFilterLast30Days,
    handleFilterDateRange,
    handleFilterSingleDate,
    handleGetAllPosts,
    handleGoPrevPage,
    handleGoNextPage,
    handleRetryRow,
    parsedGroupLines,
    isGroupIndexSelected,
    toggleGroupSelection,
    toggleSelectAllGroupsOnPage,
    groupsTotalCount,
    groupsTotalPages,
    groupsSafePage,
    groupsPageStart,
    groupsPageEnd,
    paginatedGroupRows,
    handleGroupsGoPrevPage,
    handleGroupsGoNextPage,
  };
}

function extractStartWebhookMessage(
  data: { response_message?: string; response_preview?: string } | null | undefined,
): string {
  const fromField = data?.response_message?.trim();
  if (fromField) return fromField;

  const preview = data?.response_preview?.trim();
  if (!preview) return "Cào dữ liệu thành công.";
  try {
    const parsed: unknown = JSON.parse(preview);
    if (typeof parsed === "string" && parsed.trim()) return parsed.trim();
    if (parsed && typeof parsed === "object" && "message" in parsed) {
      const value = (parsed as { message?: unknown }).message;
      if (typeof value === "string" && value.trim()) return value.trim();
    }
  } catch {
    // fallback dùng text gốc nếu preview không phải JSON.
  }
  return preview;
}

function toCrawlResultRow(
  fallbackGroupUrl: string,
  data: CrawlDataResponse | null,
): CrawlResultRow {
  const topPost = data?.top_post ?? null;
  const groupUrl = data?.group_url || fallbackGroupUrl;
  const path = new URL(groupUrl).pathname;

  return {
    id: groupUrl,
    groupName: data?.group_name || path,
    groupPath: path,
    groupUrl,
    status: data ? "Completed" : "Failed",
    posts: data?.total_posts_scraped ?? 0,
    topAuthor: topPost?.author || null,
    date: data?.target_date ?? new Date().toISOString().slice(0, 10),
    likes: topPost ? topPost.likes.toLocaleString("vi-VN") : null,
    reposts: topPost ? topPost.reposts.toLocaleString("vi-VN") : null,
    postUrl: topPost?.post_url || null,
    errorMessage: null,
    action: data ? "view" : "retry",
  };
}

interface CrawlOneGroupParams {
  groupUrl: string;
  sessionId: string;
  email: string;
  maxPosts: number;
  targetDate: string;
}

async function crawlOneGroup({
  groupUrl,
  sessionId,
  email,
  maxPosts,
  targetDate,
}: CrawlOneGroupParams): Promise<CrawlResultRow> {
  const crawlResponse = await crawlLinkedInGroup({
    sessionId,
    email,
    groupUrl,
    maxItems: Math.max(1, Math.min(maxPosts, 500)),
    targetDate: targetDate || undefined,
  });
  const row = toCrawlResultRow(groupUrl, crawlResponse.data);

  if (crawlResponse.success && crawlResponse.data) {
    return row;
  }

  return {
    ...row,
    status: "Failed",
    action: "retry",
    errorMessage: crawlResponse.message,
  };
}
