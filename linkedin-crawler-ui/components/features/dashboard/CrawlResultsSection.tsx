"use client";

import { MaterialIcon } from "@/components/ui";

import { statusBadgeClasses, statusLabel } from "./dashboard-helpers";
import { useDashboard } from "./dashboard-context";
import { CrawlSessionsTableCore } from "./CrawlSessionsTableCore";

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
        <h2 className="text-h2 text-on-surface font-semibold">
          Kết quả Crawl
        </h2>
        
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
              onClick={d.handleGetAllPosts}
              disabled={d.isGettingAllPosts}
            >
              <MaterialIcon name="refresh" className="shrink-0 text-[18px]" />
              Làm mới
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
      />

      {d.totalResultCount > 0 ? (
        <div className="mt-xl">
          <h3 className="text-h3 text-on-surface mb-md font-semibold">
            Crawl nhóm từ dashboard
          </h3>
          <p className="text-body-sm text-on-surface-variant mb-md">
            Kết quả khi bạn chạy crawl trực tiếp trên form (không phải n8n).
          </p>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead className="border-outline-variant bg-surface-container-low border-y">
                <tr>
                  <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                    Tên nhóm
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                    Trạng thái
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                    Bài viết
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                    Tác giả nổi bật
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                    Ngày
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                    Lượt thích
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                    Chia sẻ
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md text-right font-semibold uppercase">
                    Thao tác
                  </th>
                </tr>
              </thead>
              <tbody className="divide-surface-variant divide-y">
                {d.paginatedRows.map((row) => (
                  <tr
                    key={row.id}
                    className="group hover:bg-surface-container transition-colors"
                  >
                    <td className="px-md py-md">
                      <div className="flex flex-col">
                        <span className="text-primary group-hover:underline cursor-pointer text-sm font-semibold">
                          {row.groupName}
                        </span>
                        <span className="text-on-surface-variant text-xs">
                          {row.groupPath}
                        </span>
                        {row.errorMessage && (
                          <span className="mt-1 max-w-[240px] text-xs text-error">
                            {row.errorMessage}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-md py-md">
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-bold tracking-tight uppercase ${statusBadgeClasses(row.status)}`}
                      >
                        {statusLabel(row.status)}
                      </span>
                    </td>
                    <td className="px-md py-md text-sm font-medium">
                      {row.posts.toLocaleString("vi-VN")}
                    </td>
                    <td className="px-md py-md text-sm text-on-surface">
                      {row.topAuthor ?? "—"}
                    </td>
                    <td className="px-md py-md text-sm text-on-surface-variant">
                      {row.date}
                    </td>
                    <td className="px-md py-md text-sm text-on-surface">
                      {row.likes ?? "—"}
                    </td>
                    <td className="px-md py-md text-sm text-on-surface">
                      {row.reposts ?? "—"}
                    </td>
                    <td className="px-md py-md text-right">
                      {row.action === "retry" ? (
                        <button
                          type="button"
                          className="text-on-surface-variant hover:text-primary transition-colors"
                          aria-label={`Thử lại ${row.groupName}`}
                          onClick={() => d.handleRetryRow(row.id)}
                        >
                          <MaterialIcon name="refresh" />
                        </button>
                      ) : row.postUrl ? (
                        <a
                          href={row.postUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-on-surface-variant hover:text-primary inline-flex transition-colors"
                          aria-label={`Mở bài viết nổi bật của ${row.groupName}`}
                        >
                          <MaterialIcon name="open_in_new" />
                        </a>
                      ) : (
                        <span className="text-on-surface-variant inline-flex opacity-50">
                          <MaterialIcon name="visibility" />
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="text-body-sm text-on-surface-variant mt-lg flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span>
              Hiển thị {d.pageStart}–{d.pageEnd} trong {d.totalResultCount}{" "}
              nhóm
            </span>
            <div className="flex items-center gap-base">
              <button
                type="button"
                className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
                onClick={d.handleGoPrevPage}
                disabled={d.safePage <= 1}
                aria-label="Trang trước"
              >
                <MaterialIcon name="chevron_left" />
              </button>
              <span className="text-on-surface px-md font-bold">
                {d.safePage}
              </span>
              <button
                type="button"
                className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
                onClick={d.handleGoNextPage}
                disabled={d.safePage >= d.totalPages}
                aria-label="Trang sau"
              >
                <MaterialIcon name="chevron_right" />
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
