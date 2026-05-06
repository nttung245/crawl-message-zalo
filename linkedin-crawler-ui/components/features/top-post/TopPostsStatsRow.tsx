"use client";

import { MaterialIcon } from "@/components/ui";

export function TopPostsStatsRow() {
  return (
    <div className="mb-xl grid grid-cols-1 gap-md md:grid-cols-4">
      <div className="enterprise-card rounded-lg p-md">
        <p className="font-label-md text-on-surface-variant mb-1 uppercase">
          Tổng tiếp cận
        </p>
        <div className="flex items-baseline gap-2">
          <span className="font-h2 text-h2">1.2M</span>
          <span className="text-secondary text-body-sm flex items-center gap-0.5 font-bold">
            <MaterialIcon name="arrow_upward" className="text-[14px]" />
            12%
          </span>
        </div>
      </div>
      <div className="enterprise-card rounded-lg p-md">
        <p className="font-label-md text-on-surface-variant mb-1 uppercase">
          Tỷ lệ tương tác
        </p>
        <div className="flex items-baseline gap-2">
          <span className="font-h2 text-h2">4,82%</span>
          <span className="text-secondary text-body-sm flex items-center gap-0.5 font-bold">
            <MaterialIcon name="arrow_upward" className="text-[14px]" />
            0,5%
          </span>
        </div>
      </div>
      <div className="enterprise-card rounded-lg p-md">
        <p className="font-label-md text-on-surface-variant mb-1 uppercase">
          Khối lượng nội dung
        </p>
        <div className="flex items-baseline gap-2">
          <span className="font-h2 text-h2">342</span>
          <span className="text-on-surface-variant text-body-sm">Bài/ngày</span>
        </div>
      </div>
      <div className="enterprise-card rounded-lg p-md">
        <p className="font-label-md text-on-surface-variant mb-1 uppercase">
          Sẵn sàng xuất
        </p>
        <div className="flex items-baseline gap-2">
          <span className="font-h2 text-h2">Cao</span>
          <MaterialIcon
            name="check_circle"
            filled
            className="text-secondary text-[18px]"
          />
        </div>
      </div>
    </div>
  );
}
