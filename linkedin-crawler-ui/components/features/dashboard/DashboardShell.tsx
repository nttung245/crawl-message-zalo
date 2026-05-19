"use client";

import { useDashboardCrawler } from "@/hooks/useDashboardCrawler";

import { AppPlatformProvider } from "@/components/providers/AppPlatformProvider";

import { LinkedInEngagementQueueProvider } from "@/components/features/linkedin/dashboard/linkedin-engagement-queue-context";

import { DashboardAuthGate } from "./DashboardAuthGate";
import { DashboardProvider } from "./dashboard-context";
import { DashboardSidebar } from "./DashboardSidebar";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const state = useDashboardCrawler();

  return (
    <DashboardProvider value={state}>
      <LinkedInEngagementQueueProvider>
        <AppPlatformProvider>
          <DashboardAuthGate
          email={state.email}
          password={state.password}
          setEmail={state.setEmail}
          setPassword={state.setPassword}
        >
          <div className="min-h-screen bg-background text-on-background">
            <DashboardSidebar />
            <main className="p-lg lg:ml-64">{children}</main>
          </div>
          </DashboardAuthGate>
        </AppPlatformProvider>
      </LinkedInEngagementQueueProvider>
    </DashboardProvider>
  );
}
