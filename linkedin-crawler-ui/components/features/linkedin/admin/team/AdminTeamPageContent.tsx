"use client";

import { useMemo, useState, useEffect } from "react";
import { useDashboard } from "@/components/features/dashboard/dashboard-context";
import { AdminTeamStats } from "./AdminTeamStats";
import { AdminTeamTable, MemberPerformance } from "./AdminTeamTable";
import { MaterialIcon } from "@/components/ui";
import { AddMemberModal } from "./AddMemberModal";
import {
  findKpiOverlappingWindow,
  getMonthWeekWindowContaining,
  hasKpiForCurrentMonthWeek,
} from "@/lib/kpi-month-weeks";
import {
  computeMemberActualsInYmdRange,
  computeTeamActualsSumInYmdRange,
} from "@/lib/admin-team-kpi-metrics";
import type { CrawlSessionGroup } from "@/types/api";

const NO_CRAWL_SESSIONS: CrawlSessionGroup[] = [];

function numKpi(v: unknown): number {
  const n = parseInt(String(v ?? 0), 10);
  return Number.isFinite(n) ? n : 0;
}

export function AdminTeamPageContent() {
  const {
    allPostsResult,
    teamMembersPostsResult,
    role,
    handleGetAllPosts,
    isGettingAllPosts,
    isGettingTeamMembersPosts,
    teamMembers,
    fetchTeamMembers,
    isTeamLoading,
    email,
  } = useDashboard();

  const postsDatasetForTeamKpi = useMemo((): CrawlSessionGroup[] => {
    if (role === "leader") return teamMembersPostsResult ?? NO_CRAWL_SESSIONS;
    return allPostsResult ?? NO_CRAWL_SESSIONS;
  }, [role, teamMembersPostsResult, allPostsResult]);

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [addModalOpen, setAddModalOpen] = useState(false);

  useEffect(() => {
    void fetchTeamMembers();
    handleGetAllPosts({ skipLeaderTeamPosts: true });
  }, [fetchTeamMembers, handleGetAllPosts]);

  const dedupedTeam = useMemo(() => {
    const map = new Map<string, (typeof teamMembers)[number]>();
    for (const tm of teamMembers) {
      const key = tm.email.trim().toLowerCase();
      if (!map.has(key)) map.set(key, tm);
    }
    return [...map.values()];
  }, [teamMembers]);

  const rangeStart = dateFrom.trim() || "0000-01-01";
  const rangeEnd = dateTo.trim() || "9999-12-31";
  const teamMemberEmails = useMemo(
    () => dedupedTeam.map((t) => t.email.trim()),
    [dedupedTeam],
  );

  const members = useMemo(() => {
    return dedupedTeam.map((tm): MemberPerformance => {
      const slug =
        (typeof tm.profile_slug === "string" && tm.profile_slug.trim()) ||
        tm.email.split("@")[0] ||
        "member";

      const sheetKpi = Array.isArray(tm.kpi) ? tm.kpi : [];
      const win = getMonthWeekWindowContaining(new Date());
      const hasKpiCurrentWeek = hasKpiForCurrentMonthWeek(sheetKpi, new Date());
      const kWindow = findKpiOverlappingWindow(sheetKpi, win);

      const actualsFiltered = computeMemberActualsInYmdRange(
        tm.email,
        postsDatasetForTeamKpi,
        rangeStart,
        rangeEnd,
      );

      const perf: MemberPerformance = {
        email: tm.email,
        profile_slug: slug,
        name: slug,
        status: "idle",
        sessions: actualsFiltered.sessions,
        posts: actualsFiltered.posts,
        comments: actualsFiltered.comments,
        interactions: actualsFiltered.interactions,
        sheetKpi,
        hasKpiCurrentWeek,
        kpiWindowLabel: win.labelVi,
      };

      if (kWindow) {
        const actualKpiWeek = computeMemberActualsInYmdRange(
          tm.email,
          postsDatasetForTeamKpi,
          kWindow.start_day,
          kWindow.end_day,
        );
        const hit =
          actualKpiWeek.comments >= numKpi(kWindow.total_comment) &&
          actualKpiWeek.interactions >= numKpi(kWindow.total_reaction) &&
          actualKpiWeek.posts >= numKpi(kWindow.total_post_crawl) &&
          actualKpiWeek.sessions >= numKpi(kWindow.total_session_crawl);
        if (hit) perf.status = "completed";
        else if (
          perf.sessions > 0 ||
          perf.posts > 0 ||
          perf.comments > 0 ||
          perf.interactions > 0
        ) {
          perf.status = "processing";
        }
      } else if (perf.sessions > 0 || perf.posts > 0) {
        perf.status = "processing";
      }

      return perf;
    });
  }, [dedupedTeam, postsDatasetForTeamKpi, rangeStart, rangeEnd]);

  const stats = useMemo(() => {
    const winRef = getMonthWeekWindowContaining(new Date());
    const totalTargetComments = dedupedTeam.reduce((acc, tm) => {
      const kw = findKpiOverlappingWindow(Array.isArray(tm.kpi) ? tm.kpi : [], winRef);
      return acc + numKpi(kw?.total_comment);
    }, 0);
    const totalTargetInteractions = dedupedTeam.reduce((acc, tm) => {
      const kw = findKpiOverlappingWindow(Array.isArray(tm.kpi) ? tm.kpi : [], winRef);
      return acc + numKpi(kw?.total_reaction);
    }, 0);

    const teamActuals = computeTeamActualsSumInYmdRange(
      teamMemberEmails,
      postsDatasetForTeamKpi,
      rangeStart,
      rangeEnd,
    );

    return {
      totalMembers: members.length,
      totalPosts: teamActuals.posts,
      totalComments: teamActuals.comments,
      totalInteractions: teamActuals.interactions,
      completedKpiCount: members.filter((m) => m.status === "completed").length,
      totalTargetComments,
      totalTargetInteractions,
    };
  }, [members, dedupedTeam, teamMemberEmails, postsDatasetForTeamKpi, rangeStart, rangeEnd]);

  const refreshAll = () => {
    void (async () => {
      await fetchTeamMembers();
      handleGetAllPosts({ skipLeaderTeamPosts: true });
    })();
  };

  return (
    <div className="flex flex-col gap-lg">
      {/* Page Header */}
      <div className="bg-surface-container-lowest border border-outline-variant p-lg rounded-xl flex justify-between items-start">
        <div className="flex gap-md">
          <div className="w-12 h-12 rounded-lg bg-primary-container flex items-center justify-center text-white">
            <MaterialIcon name="verified_user" className="text-3xl" />
          </div>
          <div>
            <p className="text-primary font-bold tracking-wider text-[11px] uppercase">KHÔNG GIAN LEADER</p>
            <h2 className="font-h1 text-h1 text-on-surface">Quản lý Đội ngũ & KPI</h2>
            <p className="font-body-md text-on-surface-variant mt-1"> Theo dõi thành viên, giao KPI và đối chiếu tiến độ thực tế với mục tiêu đã đề ra.</p>
          </div>
        </div>
        <span className="px-3 py-1 bg-surface-container-high rounded-full font-label-md text-primary text-[11px]">LEADER ROLE</span>
      </div>

      {/* Action Bar */}
      <div className="bg-surface-container-low p-md rounded-xl flex flex-col md:flex-row items-center justify-between gap-md">
        <div className="flex gap-md w-full md:w-auto">
          <button
            onClick={() => setAddModalOpen(true)}
            className="flex-1 md:flex-none bg-secondary text-white px-lg py-sm rounded-lg flex items-center justify-center gap-xs font-h3 hover:opacity-90 active:scale-95 transition-all"
          >
            <MaterialIcon name="person_add" filled />
            Thêm thành viên
          </button>
          <button
            onClick={() => refreshAll()}
            disabled={isGettingAllPosts || isTeamLoading || (role === "leader" && isGettingTeamMembersPosts)}
            className="flex-1 md:flex-none bg-primary text-white px-lg py-sm rounded-lg flex items-center justify-center gap-xs font-h3 hover:bg-primary-container active:scale-95 transition-all disabled:opacity-50"
          >
            <MaterialIcon
              name="refresh"
              className={isGettingAllPosts || (role === "leader" && isGettingTeamMembersPosts) ? "animate-spin" : ""}
            />
            Làm mới
          </button>
        </div>
        <div className="flex items-center gap-md bg-white border border-outline-variant px-md py-sm rounded-lg w-full md:w-auto">
          <MaterialIcon name="calendar_month" className="text-outline" />
          <input
            type="date"
            className="w-full md:w-32 border-none p-0 text-body-md focus:ring-0 bg-transparent"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
          <span className="text-outline">→</span>
          <input
            type="date"
            className="w-full md:w-32 border-none p-0 text-body-md focus:ring-0 bg-transparent"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </div>
      </div>

      <AdminTeamStats
        totalMembers={stats.totalMembers}
        totalPosts={stats.totalPosts}
        totalKpiComments={stats.totalTargetComments}
        totalKpiInteractions={stats.totalTargetInteractions}
        completedKpiCount={stats.completedKpiCount}
        actualComments={stats.totalComments}
        actualInteractions={stats.totalInteractions}
      />

      <AdminTeamTable
        members={members}
        leaderEmail={email}
        allPostsResult={postsDatasetForTeamKpi}
        onRefresh={() => refreshAll()}
      />

      <AddMemberModal
        isOpen={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        leaderEmail={email}
        onSuccess={() => void fetchTeamMembers()}
      />
    </div>
  );
}
