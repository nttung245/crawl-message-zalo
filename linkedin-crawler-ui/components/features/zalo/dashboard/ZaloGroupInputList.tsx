"use client";

import { MaterialIcon } from "@/components/ui";
import type { ZaloGroupInputRow } from "@/hooks/useZaloCrawlerFlow";

interface ZaloGroupInputListProps {
  rows: ZaloGroupInputRow[];
  disabled?: boolean;
  verifying?: boolean;
  onAddRow: () => void;
  onVerifyRows: () => void;
  onUpdateRow: (
    rowId: string,
    field: "groupName" | "sheetTab",
    value: string,
  ) => void;
  onRemoveRow: (rowId: string) => void;
}

const VERIFY_LABELS: Record<string, string> = {
  unchecked: "Chua kiem tra",
  verified: "Da xac minh",
  not_found: "Khong tim thay",
  personal_chat: "Co the la chat ca nhan",
  zalo_not_ready: "Zalo chua san sang",
  message_panel_missing: "Khong thay khung tin nhan",
  duplicate: "Bi trung",
  failed: "Loi kiem tra",
};

function verifyTone(status: string): string {
  if (status === "verified") return "border-green-200 bg-green-50 text-green-700";
  if (status === "unchecked") return "border-outline-variant bg-surface-container-high text-on-surface-variant";
  return "border-red-200 bg-red-50 text-red-700";
}

export function ZaloGroupInputList({
  rows,
  disabled = false,
  verifying = false,
  onAddRow,
  onVerifyRows,
  onUpdateRow,
  onRemoveRow,
}: ZaloGroupInputListProps) {
  const filledCount = rows.filter((row) => row.groupName.trim()).length;
  const verifiedCount = rows.filter((row) => row.verifyStatus === "verified").length;

  return (
    <div className="flex flex-col gap-md">
      <div className="flex flex-wrap items-center justify-between gap-md">
        <div>
          <h3 className="text-h3 font-semibold text-on-surface">Danh sach nhom se crawl</h3>
          <p className="text-body-sm text-on-surface-variant">
            Chon goi y tu Zalo hoac nhap tay ten nhom, sau do kiem tra nhom truoc khi chay crawl.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-sm">
          <span className="rounded-full bg-surface-container-high px-sm py-xs text-xs font-semibold text-on-surface-variant">
            {verifiedCount}/{filledCount} da xac minh
          </span>
          <button
            type="button"
            className="border-primary text-primary hover:bg-primary/10 inline-flex min-h-10 items-center gap-2 rounded-lg border px-md py-sm text-xs font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
            onClick={onVerifyRows}
            disabled={disabled || verifying || filledCount === 0}
          >
            <MaterialIcon name={verifying ? "sync" : "check_circle"} className={`text-base ${verifying ? "animate-spin" : ""}`} />
            {verifying ? "Dang kiem tra" : "Kiem tra nhom"}
          </button>
          <button
            type="button"
            className="bg-primary text-on-primary hover:bg-primary-container inline-flex min-h-10 items-center gap-2 rounded-lg px-md py-sm text-xs font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
            onClick={onAddRow}
            disabled={disabled}
          >
            <MaterialIcon name="add" className="text-base" />
            Them dong
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-sm">
        {rows.map((row, index) => (
          <div
            key={row.id}
            className="border-outline-variant bg-surface rounded-xl border p-md"
          >
            <div className="mb-sm flex flex-wrap items-center justify-between gap-sm">
              <div className="flex flex-wrap items-center gap-sm">
                <div className="text-label-md font-semibold uppercase text-on-surface-variant">
                  Nhom {index + 1}
                </div>
                <span className={`rounded-full border px-sm py-xs text-xs font-semibold ${verifyTone(row.verifyStatus)}`}>
                  {VERIFY_LABELS[row.verifyStatus] ?? VERIFY_LABELS.failed}
                </span>
              </div>
              <button
                type="button"
                className="text-on-surface-variant hover:text-error inline-flex items-center gap-1 rounded px-sm py-xs text-xs font-bold uppercase disabled:cursor-not-allowed disabled:opacity-40"
                onClick={() => onRemoveRow(row.id)}
                disabled={disabled}
              >
                <MaterialIcon name="delete" className="text-base" />
                Xoa
              </button>
            </div>

            {row.verifyMessage ? (
              <div className={`mb-sm rounded-lg border px-sm py-xs text-body-sm ${verifyTone(row.verifyStatus)}`}>
                {row.verifyMessage}
                {row.verifyStatus === "verified" && row.warnings?.includes("member_count_unknown") ? (
                  <span className="ml-1">Khong doc duoc so thanh vien, nhung da mo dung nhom.</span>
                ) : null}
              </div>
            ) : null}

            <div className="grid gap-md md:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
              <div className="flex flex-col gap-base">
                <label className="text-label-md font-semibold uppercase tracking-wide text-on-surface-variant">
                  Ten nhom Zalo
                </label>
                <input
                  className="border-outline-variant bg-surface focus:border-primary focus:ring-primary min-h-11 rounded-lg border px-md py-sm outline-none transition-all focus:ring-1 disabled:cursor-not-allowed disabled:opacity-70"
                  type="text"
                  placeholder="Vi du: Hoi chu shop online"
                  value={row.groupName}
                  onChange={(event) =>
                    onUpdateRow(row.id, "groupName", event.target.value)
                  }
                  disabled={disabled}
                />
              </div>

              <div className="flex flex-col gap-base">
                <label className="text-label-md font-semibold uppercase tracking-wide text-on-surface-variant">
                  Ten luu tru
                </label>
                <input
                  className="border-outline-variant bg-surface focus:border-primary focus:ring-primary min-h-11 rounded-lg border px-md py-sm outline-none transition-all focus:ring-1 disabled:cursor-not-allowed disabled:opacity-70"
                  type="text"
                  placeholder="Mac dinh = ten nhom"
                  value={row.sheetTab}
                  onChange={(event) =>
                    onUpdateRow(row.id, "sheetTab", event.target.value)
                  }
                  disabled={disabled}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
