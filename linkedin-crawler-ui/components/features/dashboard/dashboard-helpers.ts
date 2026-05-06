import type { CrawlResultRow } from "./types";

export function statusBadgeClasses(status: CrawlResultRow["status"]): string {
  switch (status) {
    case "Completed":
      return "bg-secondary-container/30 text-on-secondary-container";
    case "Processing":
      return "bg-primary/10 text-primary";
    case "Failed":
      return "bg-error-container text-error";
    default:
      return "bg-surface-container-high text-on-surface-variant";
  }
}

/** Tên hiển thị tạm từ URL nhóm (trước khi có tên thật từ API). */
export function deriveGroupDisplayName(groupUrl: string): string {
  try {
    const u = new URL(groupUrl);
    const m = u.pathname.match(/groups\/(\d+)/i);
    if (m?.[1]) {
      return `Nhóm ${m[1]}`;
    }
    return u.pathname || groupUrl;
  } catch {
    return groupUrl;
  }
}

export function statusLabel(status: CrawlResultRow["status"]): string {
  switch (status) {
    case "Completed":
      return "Hoàn tất";
    case "Processing":
      return "Đang xử lý";
    case "Failed":
      return "Thất bại";
    default:
      return status;
  }
}
