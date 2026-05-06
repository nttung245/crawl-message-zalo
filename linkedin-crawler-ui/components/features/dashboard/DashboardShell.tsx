"use client";

import { useDashboardCrawler } from "@/hooks/useDashboardCrawler";

import { DashboardAuthGate } from "./DashboardAuthGate";
import { DashboardHeader } from "./DashboardHeader";
import { DashboardProvider } from "./dashboard-context";
import { DashboardSidebar } from "./DashboardSidebar";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const state = useDashboardCrawler();

  return (
    <DashboardProvider value={state}>
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
    </DashboardProvider>
  );
}
