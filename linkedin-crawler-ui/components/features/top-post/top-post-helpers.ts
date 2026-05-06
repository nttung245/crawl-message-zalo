import type { TopPostStatus } from "./types";

export function topPostStatusLabel(status: TopPostStatus): string {
  switch (status) {
    case "active":
      return "Đang hot";
    case "completed":
      return "Ổn định";
    case "failed":
      return "Lỗi crawl";
    default:
      return status;
  }
}

export function topPostStatusClass(status: TopPostStatus): string {
  switch (status) {
    case "active":
      return "bg-primary/10 text-primary";
    case "completed":
      return "bg-secondary/10 text-secondary";
    case "failed":
      return "bg-error/10 text-error";
    default:
      return "bg-surface-container-high text-on-surface-variant";
  }
}
