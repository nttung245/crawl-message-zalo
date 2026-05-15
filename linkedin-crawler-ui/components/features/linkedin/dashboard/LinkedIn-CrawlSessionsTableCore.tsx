"use client";

import { useMemo, useState } from "react";

import type { CrawlSessionGroup } from "@/types/api";
import type { CrawlTableViewMode } from "@/components/features/dashboard/types";

import {
  sessionLatestDateLabel,
  shortenSessionId,
} from "@/components/features/linkedin/dashboard/LinkedIn-n8n-sheet-helpers";
import { SessionPostsModal } from "@/components/features/linkedin/dashboard/LinkedIn-SessionPostsModal";

export interface CrawlSessionsTableCoreProps {
  sessions: CrawlSessionGroup[] | null;
  emptyHint: string;
  busy?: boolean;
  loadingHint?: string;
  modalTitleSuffix?: string;
  dashboardEmail?: string | null;
  linkedinPlaywrightSessionId?: string | null;
  /** Sau reaction + webhook OK — dialog OK gọi làm mới get-all-posts. */
  refreshSessionsAfterReaction?: () => Promise<void>;
  refreshSessionsBusy?: boolean;
  tableVariant?: CrawlTableViewMode;
  /** Chỉ khi ``tableVariant === 'filtered'`` — hiển thị cột «Ngày / điều kiện lọc». */
  filterAppliedLabel?: string;
}

/**
 * Bảng phiên cào + modal chi tiết — dùng trong Kết quả Crawl.
 */
export function CrawlSessionsTableCore({
  sessions,
  emptyHint,
  busy = false,
  loadingHint = "Đang tải dữ liệu phiên từ n8n…",
  modalTitleSuffix,
  dashboardEmail = null,
  linkedinPlaywrightSessionId = null,
  refreshSessionsAfterReaction,
  refreshSessionsBusy = false,
  tableVariant = "all",
  filterAppliedLabel = "",
}: CrawlSessionsTableCoreProps) {
  const PAGE_SIZE = 8;
  const [open, setOpen] = useState<CrawlSessionGroup | null>(null);
  const [page, setPage] = useState(1);

  const isFiltered = tableVariant === "filtered";
  const colCount = isFiltered ? 6 : 5;

  const loading = busy && sessions === null;
  const loadedEmpty = !busy && sessions !== null && sessions.length === 0;
  const hasRows = !busy && sessions !== null && sessions.length > 0;
  const refreshingWithRows = busy && sessions !== null && sessions.length > 0;
  const totalRows = sessions?.length ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * PAGE_SIZE;
  const paginatedSessions = useMemo(
    () => (sessions ?? []).slice(pageStart, pageStart + PAGE_SIZE),
    [sessions, pageStart],
  );

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-outline-variant">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <thead className="bg-surface-container-low border-outline-variant border-b">
            <tr>
              <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                Phiên cào
              </th>
              <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                Email crawl
              </th>
              <th className="text-table-header text-on-surface-variant px-md py-md text-right font-semibold uppercase">
                Số nhóm / bài
              </th>
              <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                Ngày (gần nhất)
              </th>
              {isFiltered ? (
                <th className="text-table-header text-on-surface-variant max-w-[200px] px-md py-md font-semibold uppercase">
                  Ngày / điều kiện lọc
                </th>
              ) : null}
              <th className="text-table-header text-on-surface-variant px-md py-md text-right font-semibold uppercase">
                Chi tiết
              </th>
            </tr>
          </thead>
          <tbody className="divide-outline-variant divide-y">
            {loading ? (
              <tr>
                <td
                  colSpan={colCount}
                  className="text-on-surface-variant px-md py-lg text-center"
                >
                  {loadingHint}
                </td>
              </tr>
            ) : null}

            {loadedEmpty ? (
              <tr>
                <td
                  colSpan={colCount}
                  className="text-on-surface-variant px-md py-lg text-center"
                >
                  {emptyHint}
                </td>
              </tr>
            ) : null}

            {(hasRows || refreshingWithRows) &&
              paginatedSessions.map((row, rowIdx) => (
                <tr
                  key={`${row.id_session_crawl}-${pageStart + rowIdx}`}
                  className={`hover:bg-surface-container/50 transition-colors ${
                    refreshingWithRows ? "opacity-70" : ""
                  }`}
                >
                  <td className="px-md py-md">
                    <button
                      type="button"
                      onClick={() => setOpen(row)}
                      className="text-primary hover:underline text-left font-mono text-xs"
                      title={row.id_session_crawl}
                    >
                      {shortenSessionId(row.id_session_crawl)}
                    </button>
                  </td>
                  <td className="text-on-surface max-w-[200px] px-md py-md break-all">
                    {row.email_crawl || "—"}
                  </td>
                  <td className="text-on-surface px-md py-md text-right tabular-nums">
                    {row.posts_count.toLocaleString("vi-VN")}
                  </td>
                  <td className="text-on-surface-variant px-md py-md whitespace-nowrap">
                    {sessionLatestDateLabel(row)}
                  </td>
                  {isFiltered ? (
                    <td className="text-on-surface-variant max-w-[220px] px-md py-md text-xs break-words">
                      {filterAppliedLabel || "—"}
                    </td>
                  ) : null}
                  <td className="px-md py-md text-right">
                    <button
                      type="button"
                      onClick={() => setOpen(row)}
                      className="text-primary text-xs font-bold uppercase tracking-wide hover:underline"
                    >
                      Xem
                    </button>
                  </td>
                </tr>
              ))}

            {!loading && !loadedEmpty && !hasRows && !refreshingWithRows ? (
              <tr>
                <td
                  colSpan={colCount}
                  className="text-on-surface-variant px-md py-lg text-center"
                >
                  {emptyHint}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {hasRows || refreshingWithRows ? (
        <div className="text-body-sm text-on-surface-variant mt-md flex items-center justify-between gap-md">
          <span>
            Hiển thị {pageStart + 1}–
            {Math.min(pageStart + PAGE_SIZE, totalRows)} / {totalRows} phiên
          </span>
          <div className="flex items-center gap-sm">
            <button
              type="button"
              className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={safePage <= 1}
              aria-label="Trang trước"
            >
              ‹
            </button>
            <span className="text-on-surface px-md font-bold">
              {safePage}/{totalPages}
            </span>
            <button
              type="button"
              className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={safePage >= totalPages}
              aria-label="Trang sau"
            >
              ›
            </button>
          </div>
        </div>
      ) : null}

      <SessionPostsModal
        key={open?.id_session_crawl ?? "__closed__"}
        session={open}
        titleSuffix={modalTitleSuffix}
        dashboardEmail={dashboardEmail}
        linkedinPlaywrightSessionId={linkedinPlaywrightSessionId}
        onRefreshSessions={refreshSessionsAfterReaction}
        refreshSessionsBusy={refreshSessionsBusy}
        onClose={() => setOpen(null)}
      />
    </>
  );
}
