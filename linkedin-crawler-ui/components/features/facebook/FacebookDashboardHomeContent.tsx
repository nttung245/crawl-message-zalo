"use client";

import { MaterialIcon } from "@/components/ui";

/**
 * Khung feed / bảng / card / chi tiết cho Facebook — team Facebook tự triển khai tại đây
 * (hoặc tách thêm module con). Sidebar và chọn nền tảng dùng chung với LinkedIn.
 */
export function FacebookDashboardHomeContent() {
  return (
    <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-xl shadow-sm">
      <div className="mb-md flex items-center gap-3">
        <div className="bg-secondary-container/40 text-secondary flex h-12 w-12 items-center justify-center rounded-lg">
          <MaterialIcon name="database" className="text-[28px]" />
        </div>
        <div>
          <h1 className="text-h1 text-on-surface font-semibold">Facebook · Tổng quan</h1>
          <p className="text-body-sm text-on-surface-variant">
            Khu vực dành cho team Facebook: bảng, thẻ nội dung, modal chi tiết, bộ lọc riêng.
          </p>
        </div>
      </div>
      <div className="border-outline-variant bg-surface-container-low rounded-lg border border-dashed px-lg py-xl text-center">
        <p className="text-body-md text-on-surface font-medium">
          Chưa gắn feed / bảng dữ liệu Facebook
        </p>
        <p className="text-body-sm text-on-surface-variant mx-auto mt-2 max-w-xl">
          Thay component này bằng bảng và luồng của bạn. Phần shell (sidebar, chọn LinkedIn/Facebook)
          đã dùng chung — chỉ nội dung vùng chính thay đổi theo nền tảng.
        </p>
      </div>
    </div>
  );
}
