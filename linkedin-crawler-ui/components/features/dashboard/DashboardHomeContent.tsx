"use client";

import { useAppPlatform } from "@/components/providers/AppPlatformProvider";
import { FacebookDashboardHomeContent } from "@/components/features/facebook/FacebookDashboardHomeContent";
import { LinkedInDashboardHomeContent } from "@/components/features/linkedin/dashboard";

export function DashboardHomeContent() {
  const { platform } = useAppPlatform();
  if (platform === "facebook") return <FacebookDashboardHomeContent />;
  return <LinkedInDashboardHomeContent />;
}
