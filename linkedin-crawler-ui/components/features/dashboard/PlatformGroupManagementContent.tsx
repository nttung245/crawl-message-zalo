"use client";

import { useAppPlatform } from "@/components/providers/AppPlatformProvider";
import { FacebookGroupManagementPlaceholder } from "@/components/features/facebook/FacebookGroupManagementPlaceholder";
import { LinkedInGroupManagementPageContent } from "@/components/features/linkedin/group-management";

export function PlatformGroupManagementContent() {
  const { platform } = useAppPlatform();
  if (platform === "facebook") return <FacebookGroupManagementPlaceholder />;
  return <LinkedInGroupManagementPageContent />;
}
