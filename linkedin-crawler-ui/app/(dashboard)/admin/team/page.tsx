"use client";

import { useDashboard } from "@/components/features/dashboard/dashboard-context";
import { AdminTeamPageContent } from "@/components/features/linkedin/admin/team/AdminTeamPageContent";
import { ForbiddenPage } from "@/components/features/auth/ForbiddenPage";

export default function AdminTeamPage() {
  const { role } = useDashboard();

  if (role === null) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="flex flex-col items-center gap-md">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
          <p className="text-body-lg font-bold text-on-surface-variant">Đang kiểm tra quyền truy cập...</p>
        </div>
      </div>
    );
  }

  if (role !== "leader") {
    return <ForbiddenPage />;
  }

  return <AdminTeamPageContent />;
}
