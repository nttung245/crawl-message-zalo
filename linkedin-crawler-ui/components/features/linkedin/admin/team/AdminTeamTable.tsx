"use client";

import { useState } from "react";
import { MaterialIcon } from "@/components/ui";
import type { CrawlSessionGroup } from "@/types/api";
import { AssignKpiModal, type KpiModalMode } from "./AssignKpiModal";

export interface MemberPerformance {
  email: string;
  /** Slug LinkedIn / sheet — bắt buộc khi gọi API giao KPI. */
  profile_slug: string;
  name: string;
  avatar?: string;
  status: "completed" | "processing" | "idle" | "error";
  sessions: number;
  posts: number;
  comments: number;
  interactions: number;
  /** KPI trên sheet (merge khi giao/sửa). */
  sheetKpi: unknown[];
  /** Đã có KPI giao nhau với tuần-hiện-tại-trong-tháng. */
  hasKpiCurrentWeek: boolean;
  kpiWindowLabel: string;
}

interface AdminTeamTableProps {
  members: MemberPerformance[];
  /** Email leader — gửi kèm khi giao/sửa KPI (email_leader trên sheet/n8n). */
  leaderEmail: string;
  /** Feed get-all-posts — so sánh KPI / modal xem KPI. */
  allPostsResult: CrawlSessionGroup[] | null;
  onRefresh?: () => void;
}

const kpiBtn =
  "inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:border-zinc-500 dark:hover:bg-zinc-800";

export function AdminTeamTable({
  members,
  leaderEmail,
  allPostsResult,
  onRefresh,
}: AdminTeamTableProps) {
  const [kpiModal, setKpiModal] = useState<{
    email: string;
    profileSlug: string;
    sheetKpi: unknown[];
    mode: KpiModalMode;
  } | null>(null);

  const openKpiModal = (member: MemberPerformance, mode: KpiModalMode) => {
    setKpiModal({
      email: member.email,
      profileSlug: member.profile_slug,
      sheetKpi: member.sheetKpi,
      mode,
    });
  };

  const closeKpiModal = () => setKpiModal(null);

  const exportCsv = () => {
    const headers = [
      "email",
      "profile_slug",
      "sessions",
      "posts",
      "comments",
      "interactions",
      "status",
      "has_kpi_week",
    ];
    const rows = members.map((m) =>
      [
        m.email,
        m.profile_slug,
        m.sessions,
        m.posts,
        m.comments,
        m.interactions,
        m.status,
        m.hasKpiCurrentWeek ? "yes" : "no",
      ].join(","),
    );
    const blob = new Blob([[headers.join(","), ...rows].join("\n")], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `team-kpi-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="bg-white border border-outline-variant rounded-xl overflow-hidden">
        <div className="p-lg border-b border-outline-variant flex justify-between items-center">
          <h3 className="font-h2 text-h2">Quản lý Hiệu suất Đội ngũ</h3>
          <div className="flex gap-sm">
            <button
              onClick={exportCsv}
              className="px-md py-sm border border-outline-variant rounded text-body-md hover:bg-surface-container-low transition-colors"
            >
              Xuất CSV
            </button>
            <button
              onClick={onRefresh}
              className="px-md py-sm bg-primary-container text-white rounded text-body-md flex items-center gap-xs"
            >
              <MaterialIcon name="sync" className="text-sm" />
              Làm mới bảng
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead className="bg-surface-container-low">
              <tr>
                <th className="p-md font-table-header text-on-surface-variant uppercase tracking-wider">EMAIL</th>
                <th className="p-md font-table-header text-on-surface-variant uppercase tracking-wider">TÊN</th>
                <th className="p-md font-table-header text-on-surface-variant uppercase tracking-wider">PHIÊN</th>
                <th className="p-md font-table-header text-on-surface-variant uppercase tracking-wider">BÀI VIẾT</th>
                <th className="p-md font-table-header text-on-surface-variant uppercase tracking-wider">TRẠNG THÁI</th>
                <th className="p-md font-table-header text-on-surface-variant uppercase tracking-wider">KPI </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant">
              {members.map((m) => (
                <tr key={m.email} className="hover:bg-surface-container-lowest transition-colors">
                  <td className="p-md text-body-md font-mono text-on-surface-variant truncate max-w-[200px]">
                    {m.email}
                  </td>
                  <td className="p-md">
                    <div className="flex items-center gap-sm">
                      <div className="w-8 h-8 rounded-full bg-primary-fixed flex items-center justify-center text-primary font-bold text-xs">
                        {m.avatar ? (
                          <img src={m.avatar} alt={m.name} className="h-full w-full object-cover rounded-full" />
                        ) : (
                          m.name.substring(0, 2).toUpperCase()
                        )}
                      </div>
                      <span className="font-h3 text-on-surface">{m.name}</span>
                    </div>
                  </td>
                  <td className="p-md text-body-md tabular-nums">{m.sessions}</td>
                  <td className="p-md text-body-md tabular-nums">{m.posts}</td>
                  <td className="p-md">
                    <StatusBadge status={m.status} />
                  </td>
                  <td className="p-md">
                    <div className="flex flex-col gap-xs">
                      {m.hasKpiCurrentWeek ? (
                        <>
                          <button
                            onClick={() => openKpiModal(m, "view")}
                            className="flex items-center gap-xs text-primary font-h3 text-body-sm hover:underline"
                          >
                            <MaterialIcon name="visibility" className="text-sm" />
                            Xem KPI
                          </button>
                          <button
                            onClick={() => openKpiModal(m, "edit")}
                            className="flex items-center gap-xs text-on-surface-variant font-h3 text-body-sm hover:underline"
                          >
                            <MaterialIcon name="edit" className="text-sm" />
                            Sửa KPI
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => openKpiModal(m, "assign")}
                          className="bg-primary text-white px-md py-1 rounded font-label-md text-[11px] flex items-center gap-xs active:scale-95 transition-transform"
                        >
                          <MaterialIcon name="assignment" className="text-[14px]" filled />
                          Giao KPI
                        </button>
                      )}
                      <p className="text-[10px] text-on-surface-variant italic">{m.kpiWindowLabel}</p>
                    </div>
                  </td>
                </tr>
              ))}
              {members.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-lg text-center text-on-surface-variant opacity-60">
                    Không có dữ liệu thành viên.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="p-md bg-surface-container-low border-t border-outline-variant flex justify-between items-center">
          <p className="font-body-sm text-on-surface-variant">Hiển thị {members.length} thành viên</p>
        </div>
      </div>

      {kpiModal ? (
        <AssignKpiModal
          isOpen
          onClose={closeKpiModal}
          leaderEmail={leaderEmail}
          memberEmail={kpiModal.email}
          profileSlug={kpiModal.profileSlug}
          mode={kpiModal.mode}
          sheetKpi={kpiModal.sheetKpi}
          allPostsResult={allPostsResult}
          onSuccess={onRefresh}
        />
      ) : null}
    </>
  );
}

function StatusBadge({ status }: { status: MemberPerformance["status"] }) {
  const base = "px-2 py-0.5 rounded whitespace-nowrap font-label-md text-[10px] border";
  switch (status) {
    case "completed":
      return (
        <span className={`${base} bg-secondary/10 text-secondary border-secondary/20`}>
          Hoàn thành
        </span>
      );
    case "processing":
      return (
        <span className={`${base} bg-[#fff8e1] text-[#fbc02d] border-[#ffecb3]`}>
          Đang thực hiện
        </span>
      );
    case "error":
      return (
        <span className={`${base} bg-error-container/20 text-error border-error-container/30`}>
          Lỗi
        </span>
      );
    default:
      return (
        <span className={`${base} bg-surface-container-high text-on-surface-variant border-outline-variant`}>
          Chưa bắt đầu
        </span>
      );
  }
}
