"use client";

import { MaterialIcon } from "@/components/ui";
import type {
  ZaloCrawlerSummary,
  ZaloTrackedJobState,
} from "@/hooks/useZaloCrawlerFlow";

interface ZaloCrawlProgressPanelProps {
  jobs: ZaloTrackedJobState[];
  summary: ZaloCrawlerSummary;
  onRetryGroup: (rowId: string) => Promise<void>;
}

function statusClasses(status: ZaloTrackedJobState["status"]): string {
  switch (status) {
    case "queued":
      return "bg-surface-container-high text-on-surface border-outline-variant";
    case "completed":
      return "bg-secondary-container/20 text-on-secondary-container border-secondary-container";
    case "failed":
      return "bg-error-container/40 text-error border-error-container";
    default:
      return "bg-primary/10 text-primary border-primary/20";
  }
}

export function ZaloCrawlProgressPanel({
  jobs,
  summary,
  onRetryGroup,
}: ZaloCrawlProgressPanelProps) {
  return (
    <section className="flex flex-col gap-md">
      <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
        <div className="mb-md flex items-center gap-2">
          <MaterialIcon name="monitoring" className="text-primary" />
          <h2 className="text-h3 font-semibold">Tiến độ realtime</h2>
        </div>

        <div className="mb-md grid gap-sm sm:grid-cols-2">
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              Tổng nhóm
            </div>
            <div className="text-h2 text-on-surface font-semibold">{summary.total}</div>
          </div>
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              Đang chờ
            </div>
            <div className="text-h2 text-on-surface font-semibold">{summary.queued}</div>
          </div>
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              Hoàn tất
            </div>
            <div className="text-h2 text-on-surface font-semibold">{summary.completed}</div>
          </div>
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              Tin nhắn thu thập
            </div>
            <div className="text-h2 text-on-surface font-semibold">{summary.totalMessages}</div>
          </div>
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              Ảnh tìm thấy
            </div>
            <div className="text-h2 text-on-surface font-semibold">{summary.totalImages}</div>
          </div>
        </div>

        <div className="mb-sm flex items-center justify-between gap-md">
          <span className="text-label-md text-on-surface-variant font-semibold uppercase">
            Tổng tiến độ
          </span>
          <span className="text-body-sm text-on-surface font-semibold">
            {summary.overallProgressPercent}%
          </span>
        </div>
        <div className="bg-surface-container-high h-3 overflow-hidden rounded-full">
          <div
            className="bg-primary h-full rounded-full transition-[width] duration-300"
            style={{ width: `${summary.overallProgressPercent}%` }}
          />
        </div>

        <div className="mt-sm flex flex-wrap gap-sm text-body-sm text-on-surface-variant">
          <span>Đang chờ: {summary.queued}</span>
          <span>Đang chạy: {summary.running}</span>
          <span>Thất bại: {summary.failed}</span>
        </div>
      </div>

      <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
        <div className="mb-md flex items-center gap-2">
          <MaterialIcon name="history" className="text-primary" />
          <h2 className="text-h3 font-semibold">Job theo nhóm</h2>
        </div>

        {jobs.length === 0 ? (
          <div className="border-outline-variant bg-surface rounded-xl border px-md py-lg text-body-sm text-on-surface-variant">
            Chưa có job nào được khởi tạo. Hoàn tất đăng nhập QR rồi chạy crawl để xem tiến độ theo nhóm.
          </div>
        ) : (
          <div className="flex flex-col gap-sm">
            {jobs.map((job) => (
              <div
                key={job.jobId}
                className="border-outline-variant bg-surface rounded-xl border p-md"
              >
                <div className="mb-sm flex flex-wrap items-start justify-between gap-sm">
                  <div>
                    <div className="text-body-md text-on-surface font-semibold">
                      {job.groupName}
                    </div>
                    <div className="text-body-sm text-on-surface-variant">
                      Tab Sheets: {job.sheetTab || "Theo tên nhóm"}
                    </div>
                  </div>
                  <div
                    className={`rounded-full border px-sm py-xs text-xs font-bold uppercase ${statusClasses(job.status)}`}
                  >
                    {job.stalled && job.status === "running"
                      ? "Stalled"
                      : job.status}
                  </div>
                </div>

                <div className="grid gap-sm sm:grid-cols-3">
                  <div className="text-body-sm text-on-surface-variant">
                    Tin nhắn:{" "}
                    <span className="text-on-surface font-semibold">
                      {job.progress.messages_collected}
                    </span>
                  </div>
                  <div className="text-body-sm text-on-surface-variant">
                    Ảnh:{" "}
                    <span className="text-on-surface font-semibold">
                      {job.progress.images_found}
                    </span>
                  </div>
                  <div className="text-body-sm text-on-surface-variant">
                    Mốc cũ nhất:{" "}
                    <span className="text-on-surface font-semibold">
                      {job.progress.oldest_message_date || "Chưa có"}
                    </span>
                  </div>
                </div>

                {job.error ? (
                  <div className="border-error-container bg-error-container/40 text-error mt-sm rounded-lg border px-md py-sm text-body-sm">
                    {job.error}
                  </div>
                ) : null}

                <div className="mt-sm flex flex-wrap items-center gap-sm">
                  {job.sheetUrl ? (
                    <a
                      href={job.sheetUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary inline-flex items-center gap-1 text-sm font-semibold hover:underline"
                    >
                      <MaterialIcon name="open_in_new" className="text-base" />
                      Mở Google Sheets
                    </a>
                  ) : null}
                  {job.status === "failed" ? (
                    <button
                      type="button"
                      className="border-outline-variant bg-surface hover:bg-surface-container-high rounded-lg border px-md py-xs text-xs font-bold uppercase"
                      onClick={() => void onRetryGroup(job.rowId)}
                    >
                      Thử lại
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
