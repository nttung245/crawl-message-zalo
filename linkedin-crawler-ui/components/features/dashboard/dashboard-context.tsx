"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { DashboardCrawlerValue } from "@/hooks/useDashboardCrawler";

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
  return (
    <DashboardContext.Provider value={value}>
      {children}
    </DashboardContext.Provider>
  );
}
