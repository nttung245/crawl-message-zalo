"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAppPlatform } from "@/components/providers/AppPlatformProvider";
import { useDashboard } from "@/components/features/dashboard/dashboard-context";
import { FacebookGroupManagementPlaceholder } from "@/components/features/facebook/FacebookGroupManagementPlaceholder";
import { LinkedInGroupManagementPageContent } from "@/components/features/linkedin/group-management";

export function PlatformGroupManagementContent() {
  const { platform } = useAppPlatform();
  const d = useDashboard();
  const router = useRouter();

  useEffect(() => {
    if (platform === "linkedin" && d.role === "leader") {
      router.replace("/admin/team");
    }
  }, [platform, d.role, router]);

  if (platform === "facebook") return <FacebookGroupManagementPlaceholder />;

  if (platform === "linkedin" && d.role === "leader") {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center gap-md text-on-surface-variant">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-body-md font-medium">Đang chuyển đến Quản lý đội ngũ…</p>
      </div>
    );
  }

  return <LinkedInGroupManagementPageContent />;
}
