"use client";

import { useEffect, useMemo, useState } from "react";

import { MaterialIcon } from "@/components/ui";
import {
  normalizeN8nGroupsList,
  type ManagedGroupRow,
} from "@/lib/LinkedIn-n8n-groups-normalize";
import { getAllN8nGroups } from "@/services/linkedinCrawlerService";

import { useDashboard } from "@/components/features/dashboard/dashboard-context";

export function CrawlerConfigCard() {
  const PICKER_PAGE_SIZE = 8;
const d = useDashboard();

useEffect(() => {
  if (d.role === "member") {
    d.fetchMyKpi();
    d.handleGetAllPosts();
  }
}, [d.email, d.role]);

const [pickerOpen, setPickerOpen] = useState(false);
const [pickerBusy, setPickerBusy] = useState(false);
const [pickerError, setPickerError] = useState<string | null>(null);
const [pickerRows, setPickerRows] = useState<ManagedGroupRow[]>([]);
const [pickedUrls, setPickedUrls] = useState<Set<string>>(new Set());
const [pickerPage, setPickerPage] = useState(1);
const [selectedType, setSelectedType] = useState<string>("all");

const selectedPreview = useMemo(() => {
  return d.groupUrls
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}, [d.groupUrls]);

const pickerTypeOptions = useMemo(() => {
  const types = pickerRows
    .map((row) => row.type?.trim())
    .filter((type): type is string => Boolean(type));

  return Array.from(new Set(types));
}, [pickerRows]);

const filteredPickerRows = useMemo(() => {
  if (selectedType === "all") return pickerRows;

  return pickerRows.filter((row) => row.type === selectedType);
}, [pickerRows, selectedType]);

const pickerTotalPages = Math.max(
  1,
  Math.ceil(filteredPickerRows.length / PICKER_PAGE_SIZE),
);

const pickerSafePage = Math.min(pickerPage, pickerTotalPages);
const pickerPageStart = (pickerSafePage - 1) * PICKER_PAGE_SIZE;

const pickerPageRows = filteredPickerRows.slice(
  pickerPageStart,
  pickerPageStart + PICKER_PAGE_SIZE,
);

const openGroupPicker = async () => {
  const email = d.email.trim();

  if (!email) {
    setPickerError("Nhập Email (LinkedIn) trước khi chọn danh sách nhóm.");
    return;
  }

  setPickerOpen(true);
  setPickerBusy(true);
  setPickerPage(1);
  setPickerError(null);
  setSelectedType("all");

  try {
    const res = await getAllN8nGroups({ email });

    if (!res.success) {
      throw new Error(res.message || "Không tải được danh sách nhóm.");
    }

    const rows = normalizeN8nGroupsList(res.data?.groups ?? res.data?.parsed);

    setPickerRows(rows);

    const pre = new Set(selectedPreview);
    setPickedUrls(pre);
  } catch (e) {
    setPickerRows([]);
    setPickerError(
      e instanceof Error ? e.message : "Lỗi tải danh sách nhóm.",
    );
  } finally {
    setPickerBusy(false);
  }
};

const togglePick = (url: string) => {
  setPickedUrls((prev) => {
    const next = new Set(prev);

    if (next.has(url)) {
      next.delete(url);
    } else {
      next.add(url);
    }

    return next;
  });
};

const applyPickedGroups = () => {
  const urls = pickerRows
    .map((r) => r.url_group)
    .filter((u) => pickedUrls.has(u));

  d.setGroupUrls(urls.join("\n"));
  setPickerOpen(false);
};

const togglePickAll = () => {
  if (filteredPickerRows.length === 0) return;

  const allSelected = filteredPickerRows.every((row) =>
    pickedUrls.has(row.url_group),
  );

  setPickedUrls((prev) => {
    const next = new Set(prev);

    if (allSelected) {
      filteredPickerRows.forEach((row) => {
        next.delete(row.url_group);
      });

      return next;
    }

    filteredPickerRows.forEach((row) => {
      next.add(row.url_group);
    });

    return next;
  });
};

  return (
    <section className="flex flex-col gap-md">
      <div className="border-outline-variant bg-surface-container-lowest flex flex-col gap-md rounded-xl border p-lg shadow-sm">
        <div className="border-surface-variant mb-sm flex items-center gap-2 border-b pb-md">
          <MaterialIcon name="info" className="shrink-0 text-primary" />
          <h2 className="text-h3 font-semibold">Thông tin crawler</h2>
        </div>
        <div className="grid grid-cols-1 gap-md">
          <div className="flex flex-col gap-base">
            <label
              htmlFor={d.emailId}
              className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase"
            >
              Email (LinkedIn)
            </label>
            <input
              id={d.emailId}
              className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
              placeholder="example@congty.com"
              type="email"
              value={d.email}
              onChange={(e) => d.setEmail(e.target.value)}
              autoComplete="username"
              disabled={d.isCrawling}
            />
          </div>
          <div className="flex flex-col gap-base">
            <label
              htmlFor={d.passwordId}
              className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase"
            >
              Mật khẩu
            </label>
            <input
              id={d.passwordId}
              className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
              placeholder="••••••••••••"
              type="password"
              value={d.password}
              onChange={(e) => d.setPassword(e.target.value)}
              autoComplete="current-password"
              disabled={d.isCrawling}
            />
          </div>
          <div className="grid grid-cols-2 gap-md">
            <div className="flex flex-col gap-base">
              <label
                htmlFor={d.maxPostsId}
                className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase"
              >
                Tối đa bài viết
              </label>
              <input
                id={d.maxPostsId}
                className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                type="number"
                min={1}
                value={d.maxPosts}
                onChange={(e) =>
                  d.setMaxPosts(Number.parseInt(e.target.value, 10) || 0)
                }
                disabled={d.isCrawling}
              />
            </div>
            <div className="flex flex-col gap-base">
              <label
                htmlFor={d.targetDateId}
                className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase"
              >
                Ngày mục tiêu
              </label>
              <input
                id={d.targetDateId}
                className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                type="date"
                value={d.targetDate}
                onChange={(e) => d.setTargetDate(e.target.value)}
                disabled={d.isCrawling}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-md">
            <div className="flex flex-col gap-base">
              <label
                htmlFor={d.modeId}
                className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase"
              >
                Chế độ
              </label>
              <select
                id={d.modeId}
                className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                value={d.mode}
                onChange={(e) =>
                  d.setMode(e.target.value as "Detailed" | "Fast")
                }
                disabled={d.isCrawling}
              >
                <option value="Detailed">Chi tiết</option>
                <option value="Fast">Nhanh</option>
              </select>
            </div>
            <div className="flex flex-col gap-base">
              <label
                htmlFor={d.delayId}
                className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase"
              >
                Độ trễ (giây)
              </label>
              <input
                id={d.delayId}
                className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                type="number"
                min={0}
                value={d.delaySec}
                onChange={(e) =>
                  d.setDelaySec(Number.parseInt(e.target.value, 10) || 0)
                }
                disabled={d.isCrawling}
              />
            </div>
          </div>
          <div className="flex flex-col gap-base">
            <label
              htmlFor={d.urlsId}
              className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase"
            >
              URL nhóm LinkedIn
            </label>
            <textarea
              id={d.urlsId}
              className="border-outline-variant bg-surface focus:border-primary focus:ring-primary resize-none rounded-lg border px-md py-sm font-mono text-sm transition-all outline-none focus:ring-1"
              placeholder="Chọn nhóm từ popup để đưa vào payload /start"
              rows={5}
              value={d.groupUrls}
              readOnly
              onClick={() => void openGroupPicker()}
              disabled={d.isCrawling || pickerBusy}
            />
            <div className="flex items-center justify-between gap-md">
              <p className="text-body-sm text-on-surface-variant">
                Đã chọn{" "}
                <span className="font-semibold text-on-surface">
                  {selectedPreview.length}
                </span>{" "}
                nhóm.
              </p>
              <button
                type="button"
                className="border-outline-variant bg-surface hover:bg-surface-container-high rounded-lg border px-md py-xs text-xs font-bold uppercase"
                onClick={() => void openGroupPicker()}
                disabled={d.isCrawling || pickerBusy}
              >
                {pickerBusy ? "Đang tải nhóm..." : "Chọn nhóm từ danh sách"}
              </button>
            </div>
          </div>
        </div>
        {(d.feedbackMessage || d.errorMessage) && (
          <div
            className={`rounded-lg border px-md py-sm text-body-sm ${
              d.errorMessage
                ? "border-error-container bg-error-container/40 text-error"
                : "border-secondary-container bg-secondary-container/20 text-on-secondary-container"
            }`}
            role={d.errorMessage ? "alert" : "status"}
          >
            {d.errorMessage ?? d.feedbackMessage}
          </div>
        )}
        <div className="mt-md flex flex-col items-center gap-md sm:flex-row">
          <button
            type="button"
            className="bg-primary text-on-primary hover:bg-primary-container active:scale-[0.98] w-full rounded-lg py-sm font-bold transition-all disabled:cursor-not-allowed disabled:opacity-60 sm:flex-1"
            onClick={d.handleStartCrawl}
            disabled={d.isCrawling}
          >
            {d.isCrawling ? "Đang crawl..." : "Bắt đầu Crawl"}
          </button>
          <button
            type="button"
            className="border-primary text-primary hover:bg-primary/5 w-full rounded-lg border bg-transparent py-sm font-bold transition-all disabled:cursor-not-allowed disabled:opacity-60 sm:flex-1"
            onClick={d.handleValidateLinks}
            disabled={d.isCrawling}
          >
            Kiểm tra URL
          </button>
        </div>
        <button
          type="button"
          className="text-on-surface-variant hover:text-on-surface text-label-md py-xs w-full text-center font-semibold tracking-wide uppercase transition-colors"
          onClick={d.handleResetForm}
          disabled={d.isCrawling}
        >
          Đặt lại biểu mẫu
        </button>
      </div>

      {pickerOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center p-md sm:items-center"
          role="presentation"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/45 backdrop-blur-[1px]"
            aria-label="Đóng"
            onClick={() => !pickerBusy && setPickerOpen(false)}
          />
          <div
            className="border-outline-variant bg-surface relative z-10 w-[min(94vw,920px)] rounded-xl border p-lg shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="group-picker-title"
          >
            <h3
              id="group-picker-title"
              className="text-h3 text-on-surface font-semibold"
            >
                LỰA CHỌN NHÓM CÀO
            </h3>
            <div className="mt-sm flex flex-col gap-sm sm:flex-row sm:items-end sm:justify-between">
            <div className="flex flex-col gap-xs">
              <label className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase">
                Lọc theo loại nhóm
              </label>

              <select
                className="border-outline-variant bg-surface focus:border-primary focus:ring-primary min-w-[220px] rounded-lg border px-md py-xs text-sm transition-all outline-none focus:ring-1"
                value={selectedType}
                onChange={(e) => {
                  setSelectedType(e.target.value);
                  setPickerPage(1);
                }}
                disabled={pickerBusy || pickerRows.length === 0}
              >
                <option value="all">Tất cả loại nhóm</option>
                {pickerTypeOptions.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              className="border-outline-variant bg-surface hover:bg-surface-container-high rounded-lg border px-md py-xs text-xs font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
              onClick={togglePickAll}
              disabled={pickerBusy || filteredPickerRows.length === 0}
            >
              {filteredPickerRows.length > 0 &&
              filteredPickerRows.every((row) => pickedUrls.has(row.url_group))
                ? "Bỏ chọn tất cả"
                : "Chọn tất cả"}
            </button>
          </div>
            {pickerError ? (
              <div className="border-error-container bg-error-container/40 text-error mt-md rounded-lg border px-md py-sm text-body-sm">
                {pickerError}
              </div>
            ) : null}

            <div className="mt-md max-h-[52vh] overflow-auto rounded-lg border border-outline-variant">
              <table className="w-full min-w-[640px] border-collapse text-left text-sm">
                <thead className="bg-surface-container-low border-outline-variant border-b">
                  <tr>
                    <th className="px-md py-sm">Chọn</th>
                    <th className="px-md py-sm">URL nhóm</th>
                    <th className="px-md py-sm">Tên nhóm</th>
                    <th className="px-md py-sm">Loại</th>
                    <th className="px-md py-sm text-right">Thành viên</th>
                  </tr>
                </thead>
                <tbody className="divide-outline-variant divide-y">
                  {pickerPageRows.map((row, idx) => (
                    <tr
                      key={`${row.url_group}-${idx}`}
                      className="hover:bg-surface-container/40"
                    >
                      <td className="px-md py-sm">
                        <input
                          type="checkbox"
                          className="accent-primary size-4"
                          checked={pickedUrls.has(row.url_group)}
                          onChange={() => togglePick(row.url_group)}
                        />
                      </td>
                      <td className="px-md py-sm break-all">{row.url_group}</td>
                      <td className="px-md py-sm">{row.name_group || "—"}</td>
                      <td className="px-md py-sm">{row.type || "—"}</td>
                      <td className="px-md py-sm text-right tabular-nums">
                        {row.member.toLocaleString("vi-VN")}
                      </td>
                    </tr>
                  ))}
                  {!pickerBusy && filteredPickerRows.length === 0 ? (
                          <tr>
                            <td
                              className="text-on-surface-variant px-md py-lg text-center"
                              colSpan={5}
                            >
                              {pickerRows.length === 0
                    ? "Không có nhóm nào từ API get-group."
                    : "Không có nhóm nào phù hợp với bộ lọc."}
                </td>
              </tr>
            ) : null}
                </tbody>
              </table>
            </div>

            {pickerRows.length > 0 ? (
              <div className="text-body-sm text-on-surface-variant mt-md flex items-center justify-between gap-md">
                <span>
                 Hiển thị {pickerPageStart + 1}–
                {Math.min(
                  pickerPageStart + PICKER_PAGE_SIZE,
                  filteredPickerRows.length,
                )}{" "}
                / {filteredPickerRows.length} nhóm
                </span>
                <div className="flex items-center gap-sm">
                  <button
                    type="button"
                    className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
                    onClick={() => setPickerPage((p) => Math.max(1, p - 1))}
                    disabled={pickerSafePage <= 1}
                    aria-label="Trang trước"
                  >
                    <MaterialIcon name="chevron_left" />
                  </button>
                  <span className="text-on-surface px-md font-bold">
                    {pickerSafePage}/{pickerTotalPages}
                  </span>
                  <button
                    type="button"
                    className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
                    onClick={() =>
                      setPickerPage((p) => Math.min(pickerTotalPages, p + 1))
                    }
                    disabled={pickerSafePage >= pickerTotalPages}
                    aria-label="Trang sau"
                  >
                    <MaterialIcon name="chevron_right" />
                  </button>
                </div>
              </div>
            ) : null}

            <div className="mt-lg flex items-center justify-between gap-sm">
              <span className="text-body-sm text-on-surface-variant">
                Đã chọn {pickedUrls.size}/{pickerRows.length} nhóm
              </span>
              <div className="flex items-center gap-sm">
                <button
                  type="button"
                  className="rounded-lg px-md py-sm text-sm font-bold uppercase text-on-surface-variant"
                  onClick={() => setPickerOpen(false)}
                >
                  Hủy
                </button>
                <button
                  type="button"
                  className="bg-primary text-on-primary rounded-lg px-lg py-sm text-sm font-bold uppercase"
                  onClick={applyPickedGroups}
                >
                  Áp dụng nhóm đã chọn
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {d.crawlSuccessModalOpen ? (
// ... existing modal code
        <div
          className="fixed inset-0 z-[60] flex items-end justify-center p-md sm:items-center"
          role="presentation"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/45 backdrop-blur-[1px]"
            aria-label="Đóng"
            onClick={d.closeCrawlSuccessModal}
          />
          <div
            className="border-outline-variant bg-surface relative z-10 w-[min(92vw,520px)] rounded-xl border p-lg shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="crawl-success-title"
          >
            <h3
              id="crawl-success-title"
              className="text-h3 text-on-surface font-semibold"
            >
              Cào dữ liệu thành công
            </h3>
            <p className="text-body-sm text-on-surface-variant mt-sm whitespace-pre-line">
              {d.crawlSuccessModalMessage || "Workflow đã trả về thành công."}
            </p>
            <div className="mt-lg flex justify-end">
              <button
                type="button"
                className="bg-primary text-on-primary hover:bg-primary-container min-w-24 rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void d.confirmCrawlSuccessModal()}
                disabled={d.isGettingAllPosts}
              >
                {d.isGettingAllPosts ? "Đang làm mới..." : "OK"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
