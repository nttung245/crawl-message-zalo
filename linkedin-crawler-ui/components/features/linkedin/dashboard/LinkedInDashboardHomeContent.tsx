"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { CrawlerConfigCard } from "./LinkedIn-CrawlerConfigCard";
import { CrawlResultsSection } from "./LinkedIn-CrawlResultsSection";
import { LinkedInStats } from "../stats/LinkedInStats";
import { useDashboard } from "@/components/features/dashboard/dashboard-context";

export function LinkedInDashboardHomeContent() {
  const d = useDashboard();
  const router = useRouter();

  useEffect(() => {
    if (d.role === "leader") {
      router.replace("/admin/team");
    }
  }, [d.role, router]);

  // While permission is being checked, show a neutral loading state
  if (d.role === null) {
    return (
      <div className="flex flex-col gap-xl animate-pulse">
        <div className="h-10 w-64 rounded-lg bg-surface-container-highest" />
        <div className="h-4 w-96 rounded bg-surface-container-highest" />
        <div className="grid grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-[120px] rounded-xl border border-outline-variant bg-surface-container-low" />
          ))}
        </div>
        <div className="h-64 rounded-xl border border-outline-variant bg-surface-container-low" />
      </div>
    );
  }

  // Leader: home chỉ dùng để chuyển hướng sang /admin/team (sidebar leader chỉ còn mục quản lý đội)
  if (d.role === "leader") {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center gap-md text-on-surface-variant">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-body-md font-medium">Đang chuyển đến Quản lý đội ngũ…</p>
      </div>
    );
  }

  // Member — dashboard crawler
  return (
    <>
      <div className="mb-xl">
        <h1 className="text-h1 text-on-surface mb-xs font-semibold">
          LinkedIn Group Crawler
        </h1>
        <p className="text-body-lg text-on-surface-variant">
          Thu thập và phân tích dữ liệu từ nhiều nhóm LinkedIn một cách hiệu quả.
        </p>
      </div>

      <div className="mb-xl">
        <LinkedInStats />
      </div>

      <div className="mb-xl max-w-2xl">
        <CrawlerConfigCard />
      </div>

      <div className="mb-xl">
        <CrawlResultsSection />
      </div>
    </>
  );
}
