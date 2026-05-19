"use client";

import { MaterialIcon } from "@/components/ui";
import type { ZaloTrackedJobState } from "@/hooks/useZaloCrawlerFlow";

import { ZaloGroupResultCollapse } from "./ZaloGroupResultCollapse";

interface ZaloCrawlResultSectionProps {
  jobs: ZaloTrackedJobState[];
}

export function ZaloCrawlResultSection({
  jobs,
}: ZaloCrawlResultSectionProps) {
  return (
    <section className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
      <div className="mb-md flex items-center gap-2">
        <MaterialIcon name="article" className="text-primary" />
        <h2 className="text-h3 font-semibold">Kết quả theo nhóm</h2>
      </div>

      {jobs.length === 0 ? (
        <div className="border-outline-variant bg-surface rounded-xl border px-md py-lg text-body-sm text-on-surface-variant">
          Chưa có dữ liệu kết quả. Khi job bắt đầu chạy, mỗi nhóm sẽ xuất hiện ở đây với trạng thái, số lượng tin nhắn và liên kết Google Sheets.
        </div>
      ) : (
        <div className="flex flex-col gap-md">
          {jobs.map((job) => (
            <ZaloGroupResultCollapse key={job.jobId} job={job} />
          ))}
        </div>
      )}
    </section>
  );
}
