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
        <h2 className="text-h3 font-semibold">{"K\u1ebft qu\u1ea3 theo nh\u00f3m"}</h2>
      </div>

      {jobs.length === 0 ? (
        <div className="border-outline-variant bg-surface rounded-xl border px-md py-lg text-body-sm text-on-surface-variant">
          {"Ch\u01b0a c\u00f3 d\u1eef li\u1ec7u k\u1ebft qu\u1ea3. Khi job b\u1eaft \u0111\u1ea7u ch\u1ea1y, m\u1ed7i nh\u00f3m s\u1ebd xu\u1ea5t hi\u1ec7n \u1edf \u0111\u00e2y v\u1edbi tr\u1ea1ng th\u00e1i, s\u1ed1 l\u01b0\u1ee3ng tin nh\u1eafn v\u00e0 li\u00ean k\u1ebft Google Sheets."}
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
