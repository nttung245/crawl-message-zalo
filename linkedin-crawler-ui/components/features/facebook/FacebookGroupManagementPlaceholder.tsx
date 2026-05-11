"use client";

import { MaterialIcon } from "@/components/ui";

/** Team Facebook thay bằng màn quản lý nhóm / page thật. */
export function FacebookGroupManagementPlaceholder() {
  return (
    <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-xl shadow-sm">
      <div className="mb-md flex items-center gap-3">
        <div className="bg-secondary-container/40 text-secondary flex h-12 w-12 items-center justify-center rounded-lg">
          <MaterialIcon name="group_add" className="text-[28px]" />
        </div>
        <div>
          <h1 className="text-h1 text-on-surface font-semibold">Facebook · Quản lý nhóm</h1>
          <p className="text-body-sm text-on-surface-variant">
            Thay placeholder này bằng form và bảng quản lý của team Facebook.
          </p>
        </div>
      </div>
      <div className="border-outline-variant bg-surface-container-low rounded-lg border border-dashed px-lg py-xl text-center">
        <p className="text-body-md text-on-surface font-medium">Chưa có UI quản lý Facebook</p>
        <p className="text-body-sm text-on-surface-variant mt-2">
          Sidebar và layout giữ nguyên; chỉ nội dung trang này do nền tảng Facebook đảm nhiệm.
        </p>
      </div>
    </div>
  );
}
