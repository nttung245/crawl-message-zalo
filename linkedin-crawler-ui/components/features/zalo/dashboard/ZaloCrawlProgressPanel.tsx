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

function statusLabel(job: ZaloTrackedJobState): string {
  if (job.stalled && job.status === "running") return "stalled";
  return job.status;
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
          <h2 className="text-h3 font-semibold">{"Ti\u1ebfn \u0111\u1ed9 realtime"}</h2>
        </div>

        <div className="mb-md grid gap-sm sm:grid-cols-2">
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              {"T\u1ed5ng nh\u00f3m"}
            </div>
            <div className="text-h2 text-on-surface font-semibold">{summary.total}</div>
          </div>
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              {"\u0110ang ch\u1edd"}
            </div>
            <div className="text-h2 text-on-surface font-semibold">
              {summary.queued}
            </div>
          </div>
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              {"Ho\u00e0n t\u1ea5t"}
            </div>
            <div className="text-h2 text-on-surface font-semibold">
              {summary.completed}
            </div>
          </div>
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              {"Tin nh\u1eafn thu th\u1eadp"}
            </div>
            <div className="text-h2 text-on-surface font-semibold">
              {summary.totalMessages}
            </div>
          </div>
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              {"\u1ea2nh t\u00ecm th\u1ea5y"}
            </div>
            <div className="text-h2 text-on-surface font-semibold">
              {summary.totalImages}
            </div>
          </div>
        </div>

        <div className="mb-sm flex items-center justify-between gap-md">
          <span className="text-label-md text-on-surface-variant font-semibold uppercase">
            {"T\u1ed5ng ti\u1ebfn \u0111\u1ed9"}
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
          <span>{"\u0110ang ch\u1edd"}: {summary.queued}</span>
          <span>{"\u0110ang ch\u1ea1y"}: {summary.running}</span>
          <span>{"Th\u1ea5t b\u1ea1i"}: {summary.failed}</span>
        </div>
      </div>

      <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
        <div className="mb-md flex items-center gap-2">
          <MaterialIcon name="history" className="text-primary" />
          <h2 className="text-h2 font-semibold">{"Ti\u1ebfn \u0111\u1ed9 crawl theo nh\u00f3m"}</h2>
        </div>

        {jobs.length === 0 ? (
          <div className="border-outline-variant bg-surface rounded-xl border px-md py-lg text-body-sm text-on-surface-variant">
            {"Ch\u01b0a c\u00f3 job n\u00e0o \u0111\u01b0\u1ee3c kh\u1edfi t\u1ea1o. Ho\u00e0n t\u1ea5t \u0111\u0103ng nh\u1eadp r\u1ed3i ch\u1ea1y crawl \u0111\u1ec3 xem ti\u1ebfn \u0111\u1ed9 theo nh\u00f3m."}
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
                      {"Tab Sheets: "} {job.sheetTab || "Theo t\u00ean nh\u00f3m"}
                    </div>
                  </div>
                  <div
                    className={`rounded-full border px-sm py-xs text-xs font-bold uppercase ${statusClasses(job.status)}`}
                  >
                    <span className="inline-flex items-center gap-1.5">
                      {job.status === "running" ? (
                        <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                      ) : null}
                      {job.status === "queued" ? (
                        <span className="h-3 w-3 animate-pulse rounded-full bg-current/70" />
                      ) : null}
                      {statusLabel(job)}
                    </span>
                  </div>
                </div>

                {job.status === "running" ? (
                  <div className="mb-sm">
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-primary/15">
                      <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
                    </div>
                  </div>
                ) : null}

                <div className="grid gap-sm sm:grid-cols-3">
                  <div className="text-body-sm text-on-surface-variant">
                    {"Tin nh\u1eafn: "}
                    <span className="text-on-surface font-semibold">
                      {job.progress.messages_collected}
                    </span>
                  </div>
                  <div className="text-body-sm text-on-surface-variant">
                    {"\u1ea2nh: "}
                    <span className="text-on-surface font-semibold">
                      {job.progress.images_found}
                    </span>
                  </div>
                  <div className="text-body-sm text-on-surface-variant">
                    {"M\u1ed1c c\u0169 nh\u1ea5t: "}
                    <span className="text-on-surface font-semibold">
                      {job.progress.oldest_message_date || "Ch\u01b0a c\u00f3"}
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
                      {"M\u1edf Google Sheets"}
                    </a>
                  ) : null}
                  {job.status === "failed" ? (
                    <button
                      type="button"
                      className="border-outline-variant bg-surface hover:bg-surface-container-high rounded-lg border px-md py-xs text-xs font-bold uppercase"
                      onClick={() => void onRetryGroup(job.rowId)}
                    >
                      {"Th\u1eed l\u1ea1i"}
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
