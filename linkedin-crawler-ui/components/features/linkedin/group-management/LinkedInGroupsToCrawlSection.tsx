"use client";

import { useEffect, useRef } from "react";

import { MaterialIcon } from "@/components/ui";

import { deriveGroupDisplayName } from "@/components/features/dashboard/dashboard-helpers";
import { useDashboard } from "@/components/features/dashboard/dashboard-context";

function downloadText(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function LinkedInGroupsToCrawlSection() {
  const d = useDashboard();
  const headerCheckboxRef = useRef<HTMLInputElement>(null);

  const pageIndices = d.paginatedGroupRows.map((r) => r.globalIndex);
  const selectedOnPage = pageIndices.filter((i) => d.isGroupIndexSelected(i))
    .length;
  const allPageSelected =
    pageIndices.length > 0 && selectedOnPage === pageIndices.length;

  useEffect(() => {
    const el = headerCheckboxRef.current;
    if (!el) return;
    el.indeterminate =
      selectedOnPage > 0 && selectedOnPage < pageIndices.length;
  }, [pageIndices.length, selectedOnPage]);

  const handleExportCsv = () => {
    if (d.parsedGroupLines.length === 0) return;
    const header = "STT,Link nhóm,Tên nhóm,Chọn";
    const rows = d.parsedGroupLines.map((url, i) => {
      const name = deriveGroupDisplayName(url);
      const sel = d.isGroupIndexSelected(i) ? "1" : "0";
      const esc = (s: string) =>
        /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
      return [i + 1, esc(url), esc(name), sel].join(",");
    });
    downloadText("nhom-cao.csv", [header, ...rows].join("\n"), "text/csv;charset=utf-8");
  };

  const handleExportJson = () => {
    if (d.parsedGroupLines.length === 0) return;
    const payload = d.parsedGroupLines.map((url, i) => ({
      stt: i + 1,
      linkNhom: url,
      tenNhom: deriveGroupDisplayName(url),
      chon: d.isGroupIndexSelected(i),
    }));
    downloadText(
      "nhom-cao.json",
      JSON.stringify(payload, null, 2),
      "application/json;charset=utf-8",
    );
  };

  return (
    <section className="border-outline-variant bg-surface-container-lowest mb-xl rounded-xl border p-lg shadow-sm">
      <div className="mb-lg flex flex-col justify-between gap-md md:flex-row md:items-center">
        <div>
          <h2 className="text-h2 text-on-surface font-semibold">Nhóm cào (form cục bộ)</h2>
          <p className="text-body-sm text-on-surface-variant">
            Danh sách URL nhóm bạn nhập trong biểu mẫu Crawler trực tiếp. Chọn (tick) nhóm
            được crawl khi bấm Bắt đầu Crawl — độc lập với danh sách n8n phía trên.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-md">
          <button
            type="button"
            className="bg-surface-container-high text-on-surface-variant hover:text-on-surface flex items-center gap-2 rounded-lg px-md py-sm text-xs font-bold tracking-wider uppercase transition-all disabled:cursor-not-allowed disabled:opacity-40"
            onClick={handleExportCsv}
            disabled={d.parsedGroupLines.length === 0}
          >
            <MaterialIcon name="file_download" className="shrink-0 text-[18px]" />
            Xuất CSV
          </button>
          <button
            type="button"
            className="bg-surface-container-high text-on-surface-variant hover:text-on-surface flex items-center gap-2 rounded-lg px-md py-sm text-xs font-bold tracking-wider uppercase transition-all disabled:cursor-not-allowed disabled:opacity-40"
            onClick={handleExportJson}
            disabled={d.parsedGroupLines.length === 0}
          >
            <MaterialIcon name="code" className="shrink-0 text-[18px]" />
            Xuất JSON
          </button>
        </div>
      </div>

      {d.groupsTotalCount === 0 ? (
        <div className="border-outline-variant bg-surface-container-low rounded-xl border border-dashed px-lg py-xl text-center">
          <p className="text-body-md font-semibold text-on-surface">
            Chưa có nhóm nào
          </p>
          <p className="text-body-sm text-on-surface-variant">
            Nhập URL nhóm LinkedIn (mỗi dòng một link) trong biểu mẫu crawler để
            hiển thị tại đây.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead className="border-outline-variant bg-surface-container-low border-y">
              <tr>
                <th className="text-table-header text-on-surface-variant w-14 px-md py-md font-semibold uppercase">
                  STT
                </th>
                <th className="text-table-header text-on-surface-variant min-w-[200px] px-md py-md font-semibold uppercase">
                  Link nhóm
                </th>
                <th className="text-table-header text-on-surface-variant min-w-[140px] px-md py-md font-semibold uppercase">
                  Tên nhóm
                </th>
                <th className="text-table-header text-on-surface-variant w-20 px-md py-md text-center font-semibold uppercase">
                  <span className="sr-only">Chọn crawl</span>
                  <input
                    ref={headerCheckboxRef}
                    type="checkbox"
                    className="border-outline-variant accent-primary size-4 cursor-pointer rounded border align-middle"
                    checked={allPageSelected}
                    onChange={() => d.toggleSelectAllGroupsOnPage()}
                    aria-label="Chọn hoặc bỏ chọn tất cả nhóm trên trang này"
                  />
                </th>
              </tr>
            </thead>
            <tbody className="divide-surface-variant divide-y">
              {d.paginatedGroupRows.map((row) => (
                <tr
                  key={row.globalIndex}
                  className="group hover:bg-surface-container transition-colors"
                >
                  <td className="text-on-surface-variant px-md py-md text-sm font-medium tabular-nums">
                    {row.globalIndex + 1}
                  </td>
                  <td className="px-md py-md">
                    <a
                      href={row.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary group-hover:underline break-all text-sm font-semibold"
                    >
                      {row.url}
                    </a>
                  </td>
                  <td className="text-on-surface px-md py-md text-sm">
                    {deriveGroupDisplayName(row.url)}
                  </td>
                  <td className="px-md py-md text-center">
                    <input
                      type="checkbox"
                      className="border-outline-variant accent-primary size-4 cursor-pointer rounded border align-middle"
                      checked={d.isGroupIndexSelected(row.globalIndex)}
                      onChange={() => d.toggleGroupSelection(row.globalIndex)}
                      aria-label={`Chọn crawl nhóm ${row.globalIndex + 1}`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="text-body-sm text-on-surface-variant mt-lg flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <span>
          Hiển thị {d.groupsPageStart}–{d.groupsPageEnd} trong{" "}
          {d.groupsTotalCount} nhóm
        </span>
        <div className="flex items-center gap-base">
          <button
            type="button"
            className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
            onClick={d.handleGroupsGoPrevPage}
            disabled={d.groupsSafePage <= 1}
            aria-label="Trang trước"
          >
            <MaterialIcon name="chevron_left" />
          </button>
          <span className="text-on-surface px-md font-bold">
            {d.groupsSafePage}
          </span>
          <button
            type="button"
            className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
            onClick={d.handleGroupsGoNextPage}
            disabled={d.groupsSafePage >= d.groupsTotalPages}
            aria-label="Trang sau"
          >
            <MaterialIcon name="chevron_right" />
          </button>
        </div>
      </div>
    </section>
  );
}
