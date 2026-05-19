"use client";

import { createContext, useContext, type ReactNode } from "react";
import { usePathname } from "next/navigation";

import type { DashboardCrawlerValue } from "@/hooks/useDashboardCrawler";
import { WelcomeRoleModal } from "@/components/features/auth/WelcomeRoleModal";

const DashboardContext = createContext<DashboardCrawlerValue | null>(null);

export function useDashboard(): DashboardCrawlerValue {
  const ctx = useContext(DashboardContext);
  if (!ctx) {
    throw new Error("useDashboard must be used within DashboardProvider");
  }
  return ctx;
}

interface DashboardProviderProps {
  value: DashboardCrawlerValue;
  children: ReactNode;
}

export function DashboardProvider({ value, children }: DashboardProviderProps) {
  const pathname = usePathname();
  const skipRoleModal = pathname.startsWith("/zalo-crawl");

  return (
    <DashboardContext.Provider value={value}>
      {children}
      {skipRoleModal ? null : (
        <WelcomeRoleModal
          isOpen={value.role === null}
          onSelect={(role) => value.setRole(role)}
          confirmLeaderRoleWithSheet={value.confirmLeaderRoleWithSheet}
        />
      )}
    </DashboardContext.Provider>
  );
}
