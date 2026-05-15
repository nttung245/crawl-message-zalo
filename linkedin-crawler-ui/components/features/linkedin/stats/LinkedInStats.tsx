"use client";

import { useMemo } from "react";
import { MaterialIcon } from "@/components/ui";
import { useDashboard } from "@/components/features/dashboard/dashboard-context";
import { parseYmd, addDaysLocal } from "@/lib/date-helpers";
import {
  sessionLatestDateLabel,
  parseSheetReaction,
  countAppCommentsFromPost,
} from "@/components/features/linkedin/dashboard";

export function LinkedInStats() {
  const {
    allPostsResult,
    isGettingAllPosts,
    role,
    memberKpiTargetsForToday,
    memberKpiStats,
  } = useDashboard();

  const isMember = role === "member";

  /** Leader / fallback: 7 ngày gần nhất + cách đếm cũ (bài đã comment / reaction unique). */
  const leaderStyleStats = useMemo(() => {
    if (!allPostsResult) {
      return {
        sessions: 0,
        posts: 0,
        comments: 0,
        interactions: 0,
      };
    }

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    const limit = addDaysLocal(today, -6);

    let weeklySessions = 0;
    let weeklyPosts = 0;
    let weeklyComments = 0;

    const uniqueReactionKeys = new Set<string>();

    allPostsResult.forEach((s) => {
      const dateStr = sessionLatestDateLabel(s);
      const d = parseYmd(dateStr);

      if (d && d.getTime() >= limit.getTime()) {
        weeklySessions++;

        const posts = Array.isArray(s.posts) ? s.posts : [];
        weeklyPosts += posts.length;

        const emailCrawl = String(s.email_crawl ?? "").trim().toLowerCase();

        posts.forEach((p) => {
          if (countAppCommentsFromPost(p) > 0) {
            weeklyComments++;
          }

          const reaction = parseSheetReaction(p).kind;

          if (reaction !== null) {
            const postUrl = String(
              p["URL_Bài_Viết"] ?? p["post_url"] ?? p["postUrl"] ?? "",
            )
              .trim()
              .toLowerCase();

            if (emailCrawl && postUrl) {
              uniqueReactionKeys.add(`${emailCrawl}::${postUrl}`);
            }
          }
        });
      }
    });

    return {
      sessions: weeklySessions,
      posts: weeklyPosts,
      comments: weeklyComments,
      interactions: uniqueReactionKeys.size,
    };
  }, [allPostsResult]);

  const cards = useMemo(() => {
    const styles = [
      {
        icon: "history" as const,
        iconBg: "bg-[#0077b5]/10",
        iconColor: "text-[#0077b5]",
        progressBg: "bg-[#0077b5]",
        textColor: "text-[#0077b5]",
      },
      {
        icon: "article" as const,
        iconBg: "bg-[#97f7b6]",
        iconColor: "text-[#00522c]",
        progressBg: "bg-[#006d3c]",
        textColor: "text-[#006d3c]",
      },
      {
        icon: "chat_bubble" as const,
        iconBg: "bg-[#565a5b]/10",
        iconColor: "text-[#565a5b]",
        progressBg: "bg-[#565a5b]",
        textColor: "text-[#565a5b]",
      },
      {
        icon: "thumb_up" as const,
        iconBg: "bg-[#ffdad6]",
        iconColor: "text-[#93000a]",
        progressBg: "bg-[#ba1a1a]",
        textColor: "text-[#93000a]",
      },
    ];

    if (isMember) {
      const s = memberKpiStats;
      const k = memberKpiTargetsForToday;
      const tSess = k ? Math.max(0, k.total_session_crawl) : 0;
      const tPost = k ? Math.max(0, k.total_post_crawl) : 0;
      const tComm = k ? Math.max(0, k.total_comment) : 0;
      const tReact = k ? Math.max(0, k.total_reaction) : 0;

      return [
        {
          label: "PHIÊN CÀO",
          value: s.sessions,
          target: tSess,
          ...styles[0],
        },
        {
          label: "BÀI VIẾT",
          value: s.posts,
          target: tPost,
          ...styles[1],
        },
        {
          label: "ĐÃ BÌNH LUẬN",
          value: s.comments,
          target: tComm,
          ...styles[2],
        },
        {
          label: "ĐÃ TƯƠNG TÁC",
          value: s.interactions,
          target: tReact,
          ...styles[3],
        },
      ];
    }

    const stats = leaderStyleStats;
    return [
      {
        label: "PHIÊN CÀO",
        value: stats.sessions,
        target: 10,
        ...styles[0],
      },
      {
        label: "BÀI VIẾT",
        value: stats.posts,
        target: 20,
        ...styles[1],
      },
      {
        label: "ĐÃ BÌNH LUẬN",
        value: stats.comments,
        target: 15,
        ...styles[2],
      },
      {
        label: "ĐÃ TƯƠNG TÁC",
        value: stats.interactions,
        target: 20,
        ...styles[3],
      },
    ];
  }, [isMember, memberKpiStats, memberKpiTargetsForToday, leaderStyleStats]);

  if (isGettingAllPosts && !allPostsResult) {
    return (
      <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-[120px] animate-pulse rounded-xl border border-slate-200 bg-[#f0f4f9] p-6"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => {
        const percent =
          card.target > 0
            ? Math.min(100, Math.round((card.value / card.target) * 100))
            : 0;

        return (
          <div
            key={card.label}
            className="flex min-h-[120px] flex-col gap-3 rounded-xl border border-outline-variant bg-white p-6 shadow-sm"
          >
            <div className="flex items-start justify-between">
              <div className="flex min-w-0 flex-col">
                <span className="text-3xl font-bold text-on-surface">
                  {card.value.toLocaleString("vi-VN")}
                </span>

                <span
                  className="mt-1 truncate text-xs font-semibold uppercase tracking-wider text-on-surface-variant"
                  title={card.label}
                >
                  {card.label}
                </span>
              </div>

              <div className={`rounded-lg p-2 ${card.iconBg}`}>
                <MaterialIcon
                  name={card.icon}
                  className={`text-xl ${card.iconColor}`}
                />
              </div>
            </div>

            <div className="mt-auto w-full">
              <div className="mb-1 flex items-center justify-between">
                <span className={`text-[10px] font-bold ${card.textColor}`}>
                  {card.value.toLocaleString("vi-VN")}/{card.target} COMPLETED
                </span>

                <span className="text-[10px] font-bold text-on-surface-variant">
                  {percent}%
                </span>
              </div>

              <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-container-highest">
                <div
                  className={`h-full rounded-full ${card.progressBg}`}
                  style={{ width: `${percent}%` }}
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
