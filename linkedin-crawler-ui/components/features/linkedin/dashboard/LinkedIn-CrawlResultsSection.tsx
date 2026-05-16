"use client";

import { MaterialIcon } from "@/components/ui";

import {
  statusBadgeClasses,
  statusLabel,
} from "@/components/features/dashboard/dashboard-helpers";
import { useDashboard } from "@/components/features/dashboard/dashboard-context";
import { CrawlSessionsTableCore } from "@/components/features/linkedin/dashboard/LinkedIn-CrawlSessionsTableCore";

export function CrawlResultsSection() {
  const d = useDashboard();

  const isFiltered = d.crawlTableViewMode === "filtered";

  const busyHint = isFiltered
    ? "Đang lọc dữ liệu (/filter-data)…"
    : "Đang tải dữ liệu phiên (/get-all-posts)…";

  const emptyAll =
    "Chưa có phiên cào từ n8n. Thử «Làm mới» để gọi lại /get-all-posts.";
  const emptyFiltered =
    "Không có phiên nào khớp điều kiện filter. Bấm «Xóa lọc» để quay lại danh sách đầy đủ.";

  return (
    <section className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
      <div className="mb-md">
        <h2 className="text-h2 text-on-surface font-semibold">Kết quả Crawl</h2>
      </div>

      <div className="border-outline-variant bg-surface-container-low/50 mb-md flex flex-col gap-md rounded-lg border px-md py-md">
        <div className="flex flex-wrap items-center justify-between gap-md">
          <div className="flex flex-wrap items-center gap-x-md gap-y-sm">
            <span
              className={`rounded-full px-md py-1 text-xs font-bold uppercase tracking-wide ${
                isFiltered
                  ? "bg-secondary-container text-on-secondary-container"
                  : "bg-surface-container-high text-on-surface-variant"
              }`}
            >
              {isFiltered ? "Đang xem: đã lọc" : "Đang xem: tất cả phiên"}
            </span>
            <span className="text-body-md text-on-surface font-semibold tabular-nums">
              {d.crawlSessionsTableBusy
                ? "…"
                : `${d.displayedCrawlSessionCount.toLocaleString("vi-VN")} phiên · ${d.displayedCrawlPostCount.toLocaleString("vi-VN")} bài`}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-sm">
            {isFiltered ? (
              <>
                <button
                  type="button"
                  className="border-primary text-primary hover:bg-primary/5 rounded-lg border bg-transparent px-md py-sm text-xs font-bold uppercase tracking-wide"
                  onClick={d.showAllCrawlSessions}
                  disabled={d.isGettingAllPosts}
                >
                  Xem tất cả phiên
                </button>
                <button
                  type="button"
                  className="border-outline-variant bg-surface text-on-surface hover:bg-surface-container-high flex items-center gap-2 rounded-lg border px-md py-sm text-xs font-bold uppercase tracking-wide transition-all disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={d.handleClearCrawlFilter}
                  disabled={d.isGettingAllPosts}
                >
                  <MaterialIcon
                    name="filter_alt_off"
                    className="shrink-0 text-[18px]"
                  />
                  Xóa lọc
                </button>
              </>
            ) : null}
            <button
              type="button"
              className="bg-primary text-on-primary hover:bg-primary-container flex items-center gap-2 rounded-lg px-md py-sm text-xs font-bold tracking-wider uppercase transition-all disabled:cursor-not-allowed disabled:opacity-50"
              onClick={() => {
                d.handleGetAllPosts();
              }}
              disabled={d.isGettingAllPosts || d.isSyncingAllProgress}
              title="Lấy danh sách phiên cào mới nhất từ n8n"
            >
              <MaterialIcon name="refresh" className="shrink-0 text-[18px]" />
              Làm mới
            </button>
            <button
              type="button"
              className="border-primary text-primary hover:bg-primary/5 flex items-center gap-2 rounded-lg border bg-transparent px-md py-sm text-xs font-bold tracking-wider uppercase transition-all disabled:cursor-not-allowed disabled:opacity-50"
              onClick={d.handleSyncAllProgress}
              disabled={d.isSyncingAllProgress || d.isGettingAllPosts}
              title="Quét lại toàn bộ bài viết để cập nhật reaction và comment thực tế từ LinkedIn"
            >
              <MaterialIcon
                name="sync"
                className={`shrink-0 text-[18px] ${d.isSyncingAllProgress ? "animate-spin" : ""}`}
              />
              {d.isSyncingAllProgress ? "Đang đồng bộ…" : "Làm mới tiến độ"}
            </button>
          </div>
        </div>

        <div className="border-outline-variant flex flex-col gap-md border-t pt-md">
          <div>
            <p className="text-label-md text-on-surface-variant mb-sm font-semibold tracking-wide uppercase">
              Lọc nhanh
            </p>
            <div className="flex flex-wrap gap-sm">
              <button
                type="button"
                className="border-outline-variant bg-surface text-on-surface hover:bg-surface-container-high rounded-lg border px-md py-sm text-xs font-bold uppercase tracking-wide transition-all disabled:cursor-not-allowed disabled:opacity-50"
                onClick={d.handleFilterToday}
                disabled={d.isFiltering || d.isGettingAllPosts}
              >
                Hôm nay
              </button>
              <button
                type="button"
                className="border-outline-variant bg-surface text-on-surface hover:bg-surface-container-high rounded-lg border px-md py-sm text-xs font-bold uppercase tracking-wide transition-all disabled:cursor-not-allowed disabled:opacity-50"
                onClick={d.handleFilterYesterday}
                disabled={d.isFiltering || d.isGettingAllPosts}
              >
                Hôm qua
              </button>
              <button
                type="button"
                className="border-outline-variant bg-surface text-on-surface hover:bg-surface-container-high rounded-lg border px-md py-sm text-xs font-bold uppercase tracking-wide transition-all disabled:cursor-not-allowed disabled:opacity-50"
                onClick={d.handleFilterLast7Days}
                disabled={d.isFiltering || d.isGettingAllPosts}
              >
                7 ngày gần nhất
              </button>
              <button
                type="button"
                className="border-outline-variant bg-surface text-on-surface hover:bg-surface-container-high rounded-lg border px-md py-sm text-xs font-bold uppercase tracking-wide transition-all disabled:cursor-not-allowed disabled:opacity-50"
                onClick={d.handleFilterLast30Days}
                disabled={d.isFiltering || d.isGettingAllPosts}
              >
                30 ngày gần nhất
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-sm lg:flex-row lg:items-end lg:gap-md">
            <div className="flex min-w-0 flex-1 flex-col gap-base">
              <label
                htmlFor="crawl-results-filter-from"
                className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase"
              >
                Từ ngày
              </label>
              <input
                id="crawl-results-filter-from"
                type="date"
                className="border-outline-variant bg-surface focus:border-primary focus:ring-primary max-w-full rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                value={d.filterDateFrom}
                onChange={(e) => d.setFilterDateFrom(e.target.value)}
                disabled={d.isFiltering || d.isGettingAllPosts}
              />
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-base">
              <label
                htmlFor="crawl-results-filter-to"
                className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase"
              >
                Đến ngày
              </label>
              <input
                id="crawl-results-filter-to"
                type="date"
                className="border-outline-variant bg-surface focus:border-primary focus:ring-primary max-w-full rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                value={d.filterDateTo}
                onChange={(e) => d.setFilterDateTo(e.target.value)}
                disabled={d.isFiltering || d.isGettingAllPosts}
              />
            </div>
            <button
              type="button"
              className="bg-primary text-on-primary hover:bg-primary-container shrink-0 rounded-lg px-lg py-sm font-bold transition-all disabled:cursor-not-allowed disabled:opacity-60"
              onClick={d.handleFilterDateRange}
              disabled={d.isFiltering}
            >
              {d.isFiltering ? "Đang lọc…" : "Lọc khoảng"}
            </button>
          </div>

          <div className="flex flex-col gap-sm sm:flex-row sm:items-end sm:gap-md">
            <div className="flex min-w-0 flex-1 flex-col gap-base">
              <label
                htmlFor="crawl-results-filter-date"
                className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase"
              >
                Một ngày
              </label>
              <input
                id="crawl-results-filter-date"
                type="date"
                className="border-outline-variant bg-surface focus:border-primary focus:ring-primary max-w-full rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                value={d.filterDate}
                onChange={(e) => d.setFilterDate(e.target.value)}
                disabled={d.isFiltering || d.isGettingAllPosts}
              />
            </div>
            <button
              type="button"
              className="bg-primary text-on-primary hover:bg-primary-container shrink-0 rounded-lg px-lg py-sm font-bold transition-all disabled:cursor-not-allowed disabled:opacity-60"
              onClick={d.handleFilterSingleDate}
              disabled={d.isFiltering}
            >
              {d.isFiltering ? "Đang lọc…" : "Lọc một ngày"}
            </button>
          </div>
        </div>

        {isFiltered ? (
          <p className="text-body-sm text-on-surface-variant">
            <span className="font-semibold text-on-surface">Điều kiện: </span>
            {d.filterAppliedLabel.trim() || "—"}
          </p>
        ) : null}
      </div>

      {d.filterError ? (
        <div
          className="border-error-container bg-error-container/40 text-error mb-md rounded-lg border px-md py-sm text-body-sm"
          role="alert"
        >
          {d.filterError}
        </div>
      ) : null}

      {d.allPostsError && d.crawlTableViewMode === "all" ? (
        <div
          className="border-error-container bg-error-container/40 text-error mb-md rounded-lg border px-md py-sm text-body-sm"
          role="alert"
        >
          {d.allPostsError}
        </div>
      ) : null}

      {d.allPostsMessage && d.crawlTableViewMode === "all" ? (
        <div
          className="border-secondary-container bg-secondary-container/20 text-on-secondary-container mb-md rounded-lg border px-md py-sm text-body-sm"
          role="status"
        >
          {d.allPostsMessage}
        </div>
      ) : null}

      {d.filterMessage && d.crawlTableViewMode === "filtered" ? (
        <div
          className="border-secondary-container bg-secondary-container/20 text-on-secondary-container mb-md rounded-lg border px-md py-sm text-body-sm"
          role="status"
        >
          {d.filterMessage}
        </div>
      ) : null}

      <CrawlSessionsTableCore
        sessions={d.crawlSessionsForTable}
        busy={d.crawlSessionsTableBusy}
        loadingHint={busyHint}
        emptyHint={isFiltered ? emptyFiltered : emptyAll}
        tableVariant={d.crawlTableViewMode}
        filterAppliedLabel={d.filterAppliedLabel}
        modalTitleSuffix={isFiltered ? "(filter-data)" : "(get-all-posts)"}
        dashboardEmail={d.email?.trim() || null}
        refreshSessionsAfterReaction={d.refreshDashboardData}
        refreshSessionsBusy={d.isGettingAllPosts}
      />
    </section>
  );
}
