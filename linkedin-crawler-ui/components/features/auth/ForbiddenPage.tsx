"use client";

import Link from "next/link";
import { MaterialIcon } from "@/components/ui";

export function ForbiddenPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] px-lg text-center">
      <div className="w-24 h-24 bg-error-container text-error rounded-full flex items-center justify-center mb-lg">
        <MaterialIcon name="block" className="text-5xl" />
      </div>
      <h1 className="text-h1 font-black text-on-surface mb-md">403 - TRUY CẬP BỊ TỪ CHỐI</h1>
      <p className="text-body-lg text-on-surface-variant max-w-md mb-xl">
        Bạn không có quyền truy cập vào trang này. Khu vực này chỉ dành cho quản trị viên hoặc trưởng nhóm.
      </p>
      <Link 
        href="/"
        className="bg-primary text-on-primary px-xl py-md rounded-lg font-h3 hover:brightness-110 transition-all"
      >
        Quay lại Trang Chủ
      </Link>
    </div>
  );
}
