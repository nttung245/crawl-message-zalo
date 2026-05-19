"use client";

import type { ZaloGroupInputRow } from "@/hooks/useZaloCrawlerFlow";
import { MaterialIcon } from "@/components/ui";

interface ZaloGroupInputListProps {
  rows: ZaloGroupInputRow[];
  disabled?: boolean;
  onAddRow: () => void;
  onUpdateRow: (
    rowId: string,
    field: "groupName" | "sheetTab",
    value: string,
  ) => void;
  onRemoveRow: (rowId: string) => void;
}

export function ZaloGroupInputList({
  rows,
  disabled = false,
  onAddRow,
  onUpdateRow,
  onRemoveRow,
}: ZaloGroupInputListProps) {
  return (
    <div className="flex flex-col gap-md">
      <div className="flex items-center justify-between gap-md">
        <div>
          <h3 className="text-h3 text-on-surface font-semibold">Danh sách nhóm cần crawl</h3>
          <p className="text-body-sm text-on-surface-variant">
            Nhập tên nhóm Zalo. Tab Google Sheets có thể để trống để dùng cùng tên nhóm.
          </p>
        </div>
        <button
          type="button"
          className="bg-primary text-on-primary hover:bg-primary-container inline-flex items-center gap-2 rounded-lg px-md py-sm text-xs font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
          onClick={onAddRow}
          disabled={disabled}
        >
          <MaterialIcon name="add" className="text-base" />
          Thêm nhóm
        </button>
      </div>

      <div className="flex flex-col gap-sm">
        {rows.map((row, index) => (
          <div
            key={row.id}
            className="border-outline-variant bg-surface rounded-xl border p-md"
          >
            <div className="mb-sm flex items-center justify-between gap-sm">
              <div className="text-label-md text-on-surface-variant font-semibold uppercase">
                Nhóm {index + 1}
              </div>
              <button
                type="button"
                className="text-on-surface-variant hover:text-error inline-flex items-center gap-1 rounded px-sm py-xs text-xs font-bold uppercase disabled:cursor-not-allowed disabled:opacity-40"
                onClick={() => onRemoveRow(row.id)}
                disabled={disabled}
              >
                <MaterialIcon name="delete" className="text-base" />
                Xóa
              </button>
            </div>

            <div className="grid gap-md md:grid-cols-2">
              <div className="flex flex-col gap-base">
                <label className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase">
                  Tên nhóm Zalo
                </label>
                <input
                  className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                  type="text"
                  placeholder="Ví dụ: Hội chủ shop online"
                  value={row.groupName}
                  onChange={(event) =>
                    onUpdateRow(row.id, "groupName", event.target.value)
                  }
                  disabled={disabled}
                />
              </div>

              <div className="flex flex-col gap-base">
                <label className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase">
                  Tên tab Google Sheets
                </label>
                <input
                  className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                  type="text"
                  placeholder="Mặc định = tên nhóm"
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
