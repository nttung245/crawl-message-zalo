"use client";

import { useEffect, useMemo, useState } from "react";
import type { CrawlSessionGroup } from "@/types/api";
import { assignKpi } from "@/services/linkedinCrawlerService";
import type { KpiItem } from "@/types/api";
import {
  buildWeekPickerOptionsAroundDate,
  findKpiOverlappingWindow,
  getMonthWeekWindowContaining,
  mergeKpiPayload,
  normalizeKpiList,
  type NormalizedKpiEntry,
  type WeekPickerOption,
} from "@/lib/kpi-month-weeks";
import { computeMemberActualsInYmdRange } from "@/lib/admin-team-kpi-metrics";

export type KpiModalMode = "assign" | "edit" | "view";

interface AssignKpiModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Email leader đang đăng nhập — gửi kèm để n8n/sheet ghi đúng email_leader. */
  leaderEmail: string;
  memberEmail: string;
  profileSlug: string;
  mode: KpiModalMode;
  /** KPI đang có trên sheet (để merge khi giao/sửa). */
  sheetKpi: unknown[];
  /** Feed get-all-posts — dùng khi xem KPI so sánh thực tế. */
  allPostsResult: CrawlSessionGroup[] | null;
  onSuccess?: () => void | Promise<void>;
}

export function AssignKpiModal({
  isOpen,
  onClose,
  leaderEmail,
  memberEmail,
  profileSlug,
  mode,
  sheetKpi,
  allPostsResult,
  onSuccess,
}: AssignKpiModalProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [windowLabel, setWindowLabel] = useState("");

  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [targetSessions, setTargetSessions] = useState(10);
  const [targetPosts, setTargetPosts] = useState(50);
  const [targetComments, setTargetComments] = useState(100);
  const [targetInteractions, setTargetInteractions] = useState(200);
  /** Tuần đang xem (leader chọn) — chỉ dùng mode xem. */
  const [viewWeekStart, setViewWeekStart] = useState("");
  const [viewWeekEnd, setViewWeekEnd] = useState("");

  const weekPickerOptions = useMemo((): WeekPickerOption[] => {
    const seen = new Set<string>();
    const out: WeekPickerOption[] = [];
    for (const o of buildWeekPickerOptionsAroundDate(new Date(), 3, 3)) {
      const k = `${o.startYmd}|${o.endYmd}`;
      seen.add(k);
      out.push(o);
    }
    for (const e of normalizeKpiList(sheetKpi)) {
      const k = `${e.start_day}|${e.end_day}`;
      if (seen.has(k)) continue;
      seen.add(k);
      out.push({
        startYmd: e.start_day,
        endYmd: e.end_day,
        labelVi: `KPI sheet (${e.start_day} → ${e.end_day})`,
      });
    }
    out.sort((a, b) => a.startYmd.localeCompare(b.startYmd));
    return out;
  }, [sheetKpi]);

  useEffect(() => {
    if (!isOpen) return;
    const win = getMonthWeekWindowContaining();
    setViewWeekStart(win.startYmd);
    setViewWeekEnd(win.endYmd);
    setWindowLabel(win.labelVi);
    const overlap = findKpiOverlappingWindow(sheetKpi, win);

    if ((mode === "view" || mode === "edit") && overlap) {
      setStartDate(overlap.start_day);
      setEndDate(overlap.end_day);
      setTargetSessions(overlap.total_session_crawl);
      setTargetPosts(overlap.total_post_crawl);
      setTargetComments(overlap.total_comment);
      setTargetInteractions(overlap.total_reaction);
    } else if (mode === "assign") {
      setStartDate(win.startYmd);
      setEndDate(win.endYmd);
      setTargetSessions(10);
      setTargetPosts(50);
      setTargetComments(100);
      setTargetInteractions(200);
    }
    setError(null);
  }, [isOpen, mode, memberEmail, sheetKpi]);

  const viewWeekOverlap = useMemo((): NormalizedKpiEntry | null => {
    if (!viewWeekStart || !viewWeekEnd) return null;
    return findKpiOverlappingWindow(sheetKpi, {
      startYmd: viewWeekStart,
      endYmd: viewWeekEnd,
    });
  }, [sheetKpi, viewWeekStart, viewWeekEnd]);

  const viewWeekActuals = useMemo(() => {
    if (!viewWeekStart || !viewWeekEnd) {
      return { sessions: 0, posts: 0, comments: 0, interactions: 0 };
    }
    return computeMemberActualsInYmdRange(
      memberEmail,
      allPostsResult,
      viewWeekStart,
      viewWeekEnd,
    );
  }, [memberEmail, allPostsResult, viewWeekStart, viewWeekEnd]);

  const numT = (v: unknown) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : parseInt(String(v ?? 0), 10) || 0;
  };

  if (!isOpen) return null;

  if (mode === "view") {
    const selectedWeekOption = weekPickerOptions.find(
      (o) => o.startYmd === viewWeekStart && o.endYmd === viewWeekEnd
    );
    const displayWeekLabel = selectedWeekOption?.labelVi || (viewWeekStart && viewWeekEnd ? `${viewWeekStart} → ${viewWeekEnd}` : windowLabel);

    return (
      <div className="fixed inset-0 z-[100] bg-on-background/40 backdrop-blur-sm flex items-center justify-center p-md">
        <div className="absolute inset-0" onClick={onClose} />
        
        <div className="relative z-10 bg-surface-container-lowest w-full max-w-3xl rounded-xl shadow-2xl border border-outline-variant flex flex-col max-h-[90vh]">
          <div className="px-xl py-lg border-b border-outline-variant">
            <div className="flex justify-between items-start">
              <div>
                <h2 className="font-h1 text-h1 text-primary mb-base">Chi tiết KPI Thành viên</h2>
                <div className="flex items-center gap-sm text-on-surface-variant">
                  <span className="material-symbols-outlined text-[18px]">mail</span>
                  <p className="font-body-md text-body-md">{memberEmail}</p>
                </div>
              </div>
              <button onClick={onClose} type="button" className="p-xs hover:bg-surface-container rounded-full transition-colors">
                <span className="material-symbols-outlined text-outline">close</span>
              </button>
            </div>
            
            <div className="mt-lg flex flex-col md:flex-row md:items-center justify-between gap-md">
              <div className="flex items-center gap-xs text-primary font-bold">
                <span className="material-symbols-outlined">calendar_today</span>
                <span className="font-body-lg text-body-lg">{displayWeekLabel}</span>
              </div>
              <div className="w-full md:w-64">
                <label className="font-label-md text-label-md text-on-surface-variant mb-base block">CHỌN TUẦN XEM KPI</label>
                <div className="relative">
                  <select
                    className="w-full appearance-none bg-surface-container-low border border-outline rounded-lg px-md py-sm font-body-md text-body-md focus:ring-2 focus:ring-primary focus:border-primary outline-none"
                    value={
                      weekPickerOptions.some(
                        (o) => o.startYmd === viewWeekStart && o.endYmd === viewWeekEnd,
                      )
                        ? `${viewWeekStart}|${viewWeekEnd}`
                        : weekPickerOptions[0]
                          ? `${weekPickerOptions[0].startYmd}|${weekPickerOptions[0].endYmd}`
                          : ""
                    }
                    onChange={(e) => {
                      const v = e.target.value;
                      const [s, en] = v.split("|");
                      if (s && en) {
                        setViewWeekStart(s);
                        setViewWeekEnd(en);
                      }
                    }}
                  >
                    {weekPickerOptions.map((o) => (
                      <option key={`${o.startYmd}|${o.endYmd}`} value={`${o.startYmd}|${o.endYmd}`}>
                        {o.labelVi}
                      </option>
                    ))}
                  </select>
                  <span className="material-symbols-outlined absolute right-md top-1/2 -translate-y-1/2 pointer-events-none text-outline">expand_more</span>
                </div>
              </div>
            </div>
          </div>
          
          <div className="p-xl overflow-y-auto">
            {weekPickerOptions.length === 0 ? (
              <p className="text-body-sm text-on-surface-variant">
                Chưa có tuần để chọn. Thử làm mới sau khi sheet có KPI.
              </p>
            ) : weekPickerOptions.length > 0 && !viewWeekOverlap ? (
              <p className="text-body-sm text-error">
                Không có KPI của member trong tuần đã chọn ({viewWeekStart} → {viewWeekEnd}).
              </p>
            ) : (
              <>
                <div className="mb-lg">
                  <h3 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-widest mb-md">
                    HIỆU SUẤT THỰC TẾ SO VỚI KPI
                  </h3>
                  
                  <div className="border border-outline-variant rounded-lg overflow-hidden">
                    <table className="w-full text-left border-collapse">
                      <thead className="bg-surface-container-high">
                        <tr>
                          <th className="px-lg py-md font-table-header text-table-header text-on-surface-variant">Chỉ tiêu</th>
                          <th className="px-lg py-md font-table-header text-table-header text-on-surface-variant text-center">Thực tế</th>
                          <th className="px-lg py-md font-table-header text-table-header text-on-surface-variant text-center">Mục tiêu</th>
                          <th className="px-lg py-md font-table-header text-table-header text-on-surface-variant text-right">Trạng thái</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-outline-variant">
                        {(
                          [
                            {
                              label: "Phiên cào",
                              icon: "precision_manufacturing",
                              a: viewWeekActuals.sessions,
                              t: numT(viewWeekOverlap?.total_session_crawl),
                            },
                            {
                              label: "Bài viết",
                              icon: "article",
                              a: viewWeekActuals.posts,
                              t: numT(viewWeekOverlap?.total_post_crawl),
                            },
                            {
                              label: "Bình luận",
                              icon: "comment",
                              a: viewWeekActuals.comments,
                              t: numT(viewWeekOverlap?.total_comment),
                            },
                            {
                              label: "Tương tác",
                              icon: "thumb_up",
                              a: viewWeekActuals.interactions,
                              t: numT(viewWeekOverlap?.total_reaction),
                            },
                          ] as const
                        ).map((row) => {
                          const ok = row.t <= 0 || row.a >= row.t;
                          return (
                            <tr key={row.label} className="hover:bg-surface-container-low transition-colors">
                              <td className="px-lg py-md">
                                <div className="flex items-center gap-sm">
                                  <div className="w-8 h-8 rounded bg-primary-container/10 flex items-center justify-center text-primary">
                                    <span className="material-symbols-outlined text-[20px]">{row.icon}</span>
                                  </div>
                                  <span className="font-body-md text-body-md font-semibold">{row.label}</span>
                                </div>
                              </td>
                              <td className="px-lg py-md text-center font-h3 text-h3">{row.a.toLocaleString("vi-VN")}</td>
                              <td className="px-lg py-md text-center font-body-md text-body-md text-on-surface-variant">{row.t.toLocaleString("vi-VN")}</td>
                              <td className="px-lg py-md text-right">
                                {ok ? (
                                  <span className="inline-flex items-center px-sm py-base rounded-full bg-primary-container/20 text-primary font-label-md text-label-md uppercase">
                                    <span className="w-1.5 h-1.5 rounded-full bg-primary mr-xs"></span>
                                    Đạt
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center px-sm py-base rounded-full bg-error-container/20 text-error font-label-md text-label-md uppercase">
                                    <span className="w-1.5 h-1.5 rounded-full bg-error mr-xs"></span>
                                    Chưa đạt
                                  </span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="mt-lg p-md bg-surface-container rounded-lg border border-dashed border-outline-variant flex items-center gap-md">
                  <img alt="KPI Reference Preview" className="w-12 h-12 rounded object-cover border border-outline-variant" src="https://lh3.googleusercontent.com/aida-public/AB6AXuDzMF6lkvwugOtcErFrRBHyItEPvILCnq6CRQXSkhu7uzuX4aY1Rkrva_u3wQFMHlVB1anQEWDI_a60-bVdlY6599bnuIyx4gNjT50weEnpS2EFrG3_aQK5Ni7QNPYGZc2EDJ5LS99sh-17JdfaJA-vRSXappdy-JMgmeXcFfu4X0OSlF4VRkpQgS22KOR7LPfpYAtK494K5QsRwP_GJhZnTZTPCSdsM9lbQ4OuMBU-mb1V_W7gAb8ZpGmT4CW8CsKqL4Hepo0C9ZRV"/>
                  <div className="flex-1">
                    <p className="font-label-md text-label-md text-on-surface-variant">CHI TIẾT DỮ LIỆU CÀO</p>
                    <p className="font-body-sm text-body-sm italic">Xem lại lịch sử các phiên cào dữ liệu tự động của tuần này</p>
                  </div>
                  <button type="button" className="text-primary font-label-md text-label-md uppercase hover:underline">Chi tiết</button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  const readOnly = false;
  const title = mode === "edit" ? "Chỉnh sửa KPI" : "Giao KPI";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (readOnly) return;
    setBusy(true);
    setError(null);
    try {
      const leader = (leaderEmail || "").trim();
      if (!leader) {
        setError("Thiếu email leader. Vui lòng đăng nhập lại.");
        return;
      }
      const slug = (profileSlug || "").trim() || memberEmail.split("@")[0] || "member";
      const win = getMonthWeekWindowContaining();
      const block: NormalizedKpiEntry = {
        start_day: startDate,
        end_day: endDate,
        total_session_crawl: targetSessions,
        total_post_crawl: targetPosts,
        total_comment: targetComments,
        total_reaction: targetInteractions,
      };
      const merged = mergeKpiPayload(sheetKpi, win, block);
      const kpi: KpiItem[] = merged.map((m) => ({
        start_day: m.start_day,
        end_day: m.end_day,
        total_session_crawl: m.total_session_crawl,
        total_post_crawl: m.total_post_crawl,
        total_comment: m.total_comment,
        total_reaction: m.total_reaction,
      }));

      const res = await assignKpi({
        leader_role: "leader",
        role: "member",
        email: memberEmail,
        profile_slug: slug,
        email_leader: leader,
        kpi,
      });
      if (res.success) {
        await onSuccess?.();
        onClose();
      } else {
        setError(res.message || "Không lưu được KPI.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi hệ thống.");
    } finally {
      setBusy(false);
    }
  };

  const inputClass =
    "w-full rounded-lg border border-slate-200 bg-white px-md py-sm text-body-sm text-slate-800 outline-none transition focus:border-slate-400 focus:ring-1 focus:ring-slate-200 disabled:bg-slate-50 disabled:text-slate-500 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100 dark:focus:border-zinc-500 dark:disabled:bg-zinc-950";

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-md">
      <button
        type="button"
        className="absolute inset-0 bg-black/40 backdrop-blur-[2px]"
        aria-label="Đóng"
        onClick={onClose}
      />
      <div className="relative z-10 w-[min(92vw,520px)] rounded-2xl border border-slate-200/80 bg-white p-lg shadow-xl dark:border-zinc-700 dark:bg-zinc-900">
        <div className="mb-md border-b border-slate-100 pb-md dark:border-zinc-800">
          <h3 className="text-h3 font-semibold text-slate-900 dark:text-zinc-100">{title}</h3>
          <p className="mt-xs text-body-sm text-slate-500 dark:text-zinc-400">{memberEmail}</p>
          <p className="mt-xs text-body-xs text-slate-400 dark:text-zinc-500">{windowLabel}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-md">
          <div className="grid grid-cols-2 gap-md">
            <div className="flex flex-col gap-xs">
              <label className="text-label-md font-medium text-slate-600 dark:text-zinc-400">Từ ngày</label>
              <input
                type="date"
                className={inputClass}
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                required
                disabled={busy}
              />
            </div>
            <div className="flex flex-col gap-xs">
              <label className="text-label-md font-medium text-slate-600 dark:text-zinc-400">Đến ngày</label>
              <input
                type="date"
                className={inputClass}
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                required
                disabled={busy}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-md">
            <div className="flex flex-col gap-xs">
              <label className="text-label-md font-medium text-slate-600 dark:text-zinc-400">Phiên cào</label>
              <input
                type="number"
                className={inputClass}
                value={targetSessions}
                onChange={(e) => setTargetSessions(parseInt(e.target.value, 10) || 0)}
                required
                disabled={busy}
              />
            </div>
            <div className="flex flex-col gap-xs">
              <label className="text-label-md font-medium text-slate-600 dark:text-zinc-400">Bài viết</label>
              <input
                type="number"
                className={inputClass}
                value={targetPosts}
                onChange={(e) => setTargetPosts(parseInt(e.target.value, 10) || 0)}
                required
                disabled={busy}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-md">
            <div className="flex flex-col gap-xs">
              <label className="text-label-md font-medium text-slate-600 dark:text-zinc-400">Bình luận</label>
              <input
                type="number"
                className={inputClass}
                value={targetComments}
                onChange={(e) => setTargetComments(parseInt(e.target.value, 10) || 0)}
                required
                disabled={busy}
              />
            </div>
            <div className="flex flex-col gap-xs">
              <label className="text-label-md font-medium text-slate-600 dark:text-zinc-400">Tương tác</label>
              <input
                type="number"
                className={inputClass}
                value={targetInteractions}
                onChange={(e) => setTargetInteractions(parseInt(e.target.value, 10) || 0)}
                required
                disabled={busy}
              />
            </div>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-sm text-body-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-sm pt-md">
            <button
              type="button"
              className="rounded-lg border border-slate-200 bg-white px-lg py-sm text-body-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
              onClick={onClose}
              disabled={busy}
            >
              Hủy
            </button>
            <button
              type="submit"
              className="rounded-lg border border-slate-800 bg-slate-800 px-xl py-sm text-body-sm font-medium text-white transition hover:bg-slate-900 disabled:opacity-50 dark:border-zinc-300 dark:bg-zinc-200 dark:text-zinc-900 dark:hover:bg-white"
              disabled={busy}
            >
              {busy ? "Đang lưu…" : mode === "edit" ? "Lưu KPI" : "Giao KPI"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
