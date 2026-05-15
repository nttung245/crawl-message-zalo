"use client";

import { MaterialIcon } from "@/components/ui";

import {
  countAppCommentsFromPost,
  formatSheetCommentAutomationLabelVi,
} from "./post-sheet-engagement";

export interface SheetCommentStatusProps {
  post: Record<string, unknown>;
  /** ``chip``: modal chi tiết; ``table``: cột bảng phiên. */
  variant?: "chip" | "table";
  className?: string;
}

export function SheetCommentStatus({
  post,
  variant = "table",
  className = "",
}: SheetCommentStatusProps) {
  const count = countAppCommentsFromPost(post);
  const title = formatSheetCommentAutomationLabelVi(post);

  if (count === 0) {
    const emptyClass =
      variant === "chip"
        ? "text-on-surface-variant text-xs font-semibold"
        : "text-on-surface-variant text-[10px] font-semibold";
    return (
      <span
        className={`inline-flex min-w-0 items-center gap-2 ${emptyClass} ${className}`.trim()}
        title={title}
      >
        {variant === "chip" ? (
          <MaterialIcon
            name="comment"
            className="text-on-surface-variant shrink-0 text-[22px] leading-none"
          />
        ) : null}
        Chưa bình luận
      </span>
    );
  }

  const countLabel = count.toLocaleString("vi-VN");

  if (variant === "chip") {
    return (
      <span
        className={`inline-flex min-w-0 items-center gap-2 ${className}`.trim()}
        title={title}
      >
        <MaterialIcon
          name="comment"
          className="text-on-surface shrink-0 text-[22px] leading-none"
        />
        <span className="flex min-w-0 flex-col items-start leading-tight">
          <span className="text-on-surface text-xs font-bold tracking-tight">
            Đã có {countLabel} bình luận
          </span>
          <span className="text-on-surface-variant text-[10px] font-medium">
            trên bài viết này
          </span>
        </span>
      </span>
    );
  }

  return (
    <div
      className={`flex min-w-0 flex-col items-end gap-0.5 text-right ${className}`.trim()}
      title={title}
    >
      <span className="text-on-surface text-[10px] leading-tight font-bold">
        Đã có {countLabel} bình luận
      </span>
      <span className="text-on-surface-variant text-[9px] font-medium">
        trên bài viết này
      </span>
    </div>
  );
}
