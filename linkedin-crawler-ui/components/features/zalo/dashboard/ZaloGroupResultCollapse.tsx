"use client";

import { useState } from "react";

import { MaterialIcon } from "@/components/ui";
import type { ZaloTrackedJobState } from "@/hooks/useZaloCrawlerFlow";

import { ZaloMessageTimeline } from "./ZaloMessageTimeline";

interface ZaloGroupResultCollapseProps {
  job: ZaloTrackedJobState;
}

function chipClasses(status: ZaloTrackedJobState["status"]): string {
  switch (status) {
    case "queued":
      return "border-outline-variant bg-surface-container-high text-on-surface";
    case "completed":
      return "border-secondary-container bg-secondary-container/20 text-on-secondary-container";
    case "failed":
      return "border-error-container bg-error-container/40 text-error";
    default:
      return "border-primary/20 bg-primary/10 text-primary";
  }
}

export function ZaloGroupResultCollapse({
  job,
}: ZaloGroupResultCollapseProps) {
  const [open, setOpen] = useState(job.status !== "running");

  return (
    <div className="border-outline-variant bg-surface-container-lowest rounded-2xl border shadow-sm">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-md px-lg py-md text-left"
        onClick={() => setOpen((previous) => !previous)}
      >
        <div className="space-y-xs">
          <div className="text-h3 text-on-surface font-semibold">{job.groupName}</div>
          <div className="flex flex-wrap gap-sm">
            <span className={`rounded-full border px-sm py-xs text-xs font-bold uppercase ${chipClasses(job.status)}`}>
              {job.status}
            </span>
            <span className="bg-surface rounded-full px-sm py-xs text-xs font-semibold text-on-surface-variant">
              {job.progress.messages_collected} tin nhắn
            </span>
            <span className="bg-surface rounded-full px-sm py-xs text-xs font-semibold text-on-surface-variant">
              {job.progress.images_found} ảnh
            </span>
            <span className="bg-surface rounded-full px-sm py-xs text-xs font-semibold text-on-surface-variant">
              Cũ nhất: {job.progress.oldest_message_date || "Chưa có"}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-sm">
          {job.sheetUrl ? (
            <a
              href={job.sheetUrl}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="text-primary inline-flex items-center gap-1 text-sm font-semibold hover:underline"
            >
              <MaterialIcon name="open_in_new" className="text-base" />
              Sheet
            </a>
          ) : null}
          <MaterialIcon
            name={open ? "chevron_left" : "chevron_right"}
            className={`text-on-surface-variant transition-transform ${open ? "-rotate-90" : "rotate-0"}`}
          />
        </div>
      </button>

      {open ? (
        <div className="border-outline-variant border-t px-lg py-lg">
          <div className="mb-md grid gap-sm sm:grid-cols-2 xl:grid-cols-4">
            <div className="border-outline-variant bg-surface rounded-xl border p-md">
              <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
                Job ID
              </div>
              <div className="text-body-sm text-on-surface break-all">{job.jobId}</div>
            </div>
            <div className="border-outline-variant bg-surface rounded-xl border p-md">
              <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
                Tab Sheets
              </div>
              <div className="text-body-sm text-on-surface">{job.sheetTab}</div>
            </div>
            <div className="border-outline-variant bg-surface rounded-xl border p-md">
              <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
                Bắt đầu
              </div>
              <div className="text-body-sm text-on-surface">{job.startedAt || "Chưa có"}</div>
            </div>
            <div className="border-outline-variant bg-surface rounded-xl border p-md">
              <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
                Hoàn tất
              </div>
              <div className="text-body-sm text-on-surface">
                {job.completedAt || (job.status === "running" ? "Đang chạy" : "Chưa có")}
              </div>
            </div>
          </div>

          {job.error ? (
            <div className="border-error-container bg-error-container/40 text-error mb-md rounded-xl border px-md py-sm text-body-sm">
              {job.error}
            </div>
          ) : null}

          <ZaloMessageTimeline messages={job.messages} />
        </div>
      ) : null}
    </div>
  );
}
