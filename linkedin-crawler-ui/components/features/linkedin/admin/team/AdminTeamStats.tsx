"use client";

import { MaterialIcon } from "@/components/ui";


interface AdminTeamStatsProps {
  totalMembers: number;
  /** Tổng mục tiêu comment đã giao (theo sheet KPI). */
  totalKpiComments: number;
  totalPosts: number;
  /** Tổng mục tiêu tương tác đã giao. */
  totalKpiInteractions: number;
  completedKpiCount: number;
  /** Tổng comment thực tế (từ feed đã lọc). */
  actualComments: number;
  /** Tổng tương tác thực tế. */
  actualInteractions: number;
}

export function AdminTeamStats({
  totalMembers,
  totalKpiComments,
  totalPosts,
  totalKpiInteractions,
  completedKpiCount,
  actualComments,
  actualInteractions,
}: AdminTeamStatsProps) {
  const completionRate = totalMembers > 0 ? (completedKpiCount / totalMembers) * 100 : 0;

  return (
    <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-lg">
      {/* Stat Card 1: Members */}
      <div className="bg-white border border-outline-variant p-lg rounded-xl flex items-center gap-md">
        <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center text-primary">
          <MaterialIcon name="group" className="text-3xl" />
        </div>
        <div>
          <p className="font-label-md text-on-surface-variant">Tổng thành viên</p>
          <p className="font-h1 text-h1 text-on-surface">
            {totalMembers} <span className="text-body-sm font-normal">người</span>
          </p>
          <p className="text-secondary text-[11px] font-bold">Thành viên đội ngũ</p>
        </div>
      </div>

      {/* Stat Card 2: Comments */}
      <div className="bg-white border border-outline-variant p-lg rounded-xl flex items-center gap-md">
        <div className="w-14 h-14 rounded-full bg-secondary/10 flex items-center justify-center text-secondary">
          <MaterialIcon name="chat_bubble" className="text-3xl" filled />
        </div>
        <div>
          <p className="font-label-md text-on-surface-variant">Bình luận (Thực tế)</p>
          <p className="font-h1 text-h1 text-on-surface">{actualComments.toLocaleString("vi-VN")}</p>
          <p className="text-on-surface-variant text-[11px]">Mục tiêu: {totalKpiComments.toLocaleString("vi-VN")}</p>
        </div>
      </div>

      {/* Stat Card 3: Posts */}
      <div className="bg-white border border-outline-variant p-lg rounded-xl flex items-center gap-md">
        <div className="w-14 h-14 rounded-full bg-surface-container-highest flex items-center justify-center text-on-surface">
          <MaterialIcon name="article" className="text-3xl" />
        </div>
        <div>
          <p className="font-label-md text-on-surface-variant">Tổng bài viết</p>
          <p className="font-h1 text-h1 text-on-surface">{totalPosts.toLocaleString("vi-VN")}</p>
          <p className="text-secondary text-[11px] font-bold">Dữ liệu cào được</p>
        </div>
      </div>

      {/* Stat Card 4: Interactions */}
      <div className="bg-white border border-outline-variant p-lg rounded-xl flex items-center gap-md">
        <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center text-primary">
          <MaterialIcon name="thumb_up" className="text-3xl" />
        </div>
        <div>
          <p className="font-label-md text-on-surface-variant">Tương tác (Thực tế)</p>
          <p className="font-h1 text-h1 text-on-surface">{actualInteractions.toLocaleString("vi-VN")}</p>
          <p className="text-on-surface-variant text-[11px]">Mục tiêu: {totalKpiInteractions.toLocaleString("vi-VN")}</p>
        </div>
      </div>

      {/* Stat Card 5: KPI Progress */}
      <div className="bg-white border border-outline-variant p-lg rounded-xl flex flex-col justify-center">
        <div className="flex justify-between items-center mb-xs">
          <p className="font-label-md text-on-surface-variant">Đã hoàn thành KPI</p>
          <p className="font-label-md text-primary">
            {totalMembers > 0 ? `${completedKpiCount}/${totalMembers}` : "0/0"} ({completionRate.toFixed(0)}%)
          </p>
        </div>
        <div className="w-full bg-surface-container-high h-2 rounded-full overflow-hidden mb-sm">
          <div className="bg-primary h-full transition-all duration-500" style={{ width: `${Math.min(100, completionRate)}%` }}></div>
        </div>
        <p className="text-[10px] text-on-surface-variant">
          {totalMembers - completedKpiCount > 0 
            ? `Còn ${totalMembers - completedKpiCount} thành viên chưa đạt mục tiêu`
            : "Tất cả thành viên đã đạt KPI"}
        </p>
      </div>
    </section>
  );
}
