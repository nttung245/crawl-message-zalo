"use client";

import { MaterialIcon } from "@/components/ui";

import { useDashboard } from "./dashboard-context";

export function BentoStatsRow() {
  const d = useDashboard();

  return (
    <div className="px-lg pb-xl grid grid-cols-1 gap-lg md:grid-cols-3 lg:ml-64">
      <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
        <div className="mb-sm flex items-start justify-between gap-2">
          <MaterialIcon name="group_add" className="shrink-0 text-secondary" />
          <span className="text-secondary shrink-0 rounded bg-secondary/10 px-2 py-0.5 text-xs font-bold">
            +12.4%
          </span>
        </div>
        <h4 className="text-label-md text-on-surface-variant mb-xs font-semibold tracking-wide uppercase">
          Tổng thành viên tìm thấy
        </h4>
        <p className="text-on-surface text-2xl font-bold">{d.bentoStats.members}</p>
      </div>
      <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
        <div className="mb-sm flex items-start justify-between gap-2">
          <MaterialIcon name="speed" className="shrink-0 text-primary" />
          <span className="text-primary shrink-0 rounded bg-primary/10 px-2 py-0.5 text-xs font-bold">
            Tối ưu
          </span>
        </div>
        <h4 className="text-label-md text-on-surface-variant mb-xs font-semibold tracking-wide uppercase">
          Tốc độ Crawler
        </h4>
        <p className="text-on-surface text-2xl font-bold">
          {d.bentoStats.velocity}
        </p>
      </div>
      <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
        <div className="mb-sm flex items-start justify-between gap-2">
          <MaterialIcon name="database" className="shrink-0 text-tertiary" />
          <span className="text-tertiary shrink-0 rounded bg-tertiary/10 px-2 py-0.5 text-xs font-bold">
            Sẵn sàng
          </span>
        </div>
        <h4 className="text-label-md text-on-surface-variant mb-xs font-semibold tracking-wide uppercase">
          Sẵn sàng xuất dữ liệu
        </h4>
        <p className="text-on-surface text-2xl font-bold">
          {d.bentoStats.accuracy}
        </p>
      </div>
    </div>
  );
}
