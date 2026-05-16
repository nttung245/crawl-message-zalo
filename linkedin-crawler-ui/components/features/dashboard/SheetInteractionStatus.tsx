"use client";

import {
  ReactionToolbarGlyph,
  reactionDoneLabelVi,
} from "./linkedin-reaction-icons";
import {
  formatSheetInteractionDayLabelVi,
  formatSheetInteractionLabelVi,
  parseSheetReaction,
} from "./post-sheet-engagement";

export interface SheetInteractionStatusProps {
  post: Record<string, unknown>;
  /** ``chip``: modal chi tiết; ``table``: cột bảng phiên. */
  variant?: "chip" | "table";
  /** ``chip``: ẩn ngày trong chip khi modal hiển thị ngày ở dòng riêng bên dưới. */
  showTriggerDate?: boolean;
  className?: string;
}

export function SheetInteractionStatus({
  post,
  variant = "table",
  showTriggerDate = true,
  className = "",
}: SheetInteractionStatusProps) {
  const { kind, triggerDay } = parseSheetReaction(post);
  const dayLabel = formatSheetInteractionDayLabelVi(triggerDay);
  const title = formatSheetInteractionLabelVi(post);

  if (!kind) {
    const emptyClass =
      variant === "chip"
        ? "text-on-surface-variant text-xs font-semibold"
        : "text-on-surface-variant text-[10px] font-semibold";
    return (
      <span className={`${emptyClass} ${className}`.trim()}>Chưa tương tác</span>
    );
  }

  const kindLabel = reactionDoneLabelVi(kind);

  if (variant === "chip") {
    return (
      <span
        className={`inline-flex min-w-0 items-center gap-2 ${className}`.trim()}
        title={title}
      >
        <ReactionToolbarGlyph
          kind={kind}
          variant="mono"
          emphasis
          className="shrink-0 text-[22px] leading-none"
        />
        <span className="flex min-w-0 flex-col items-start leading-tight">
          <span className="text-on-surface text-xs font-bold tracking-tight">
            {kindLabel}
          </span>
          {showTriggerDate && dayLabel ? (
            <span className="text-on-surface-variant text-[10px] font-medium tabular-nums">
              {dayLabel}
            </span>
          ) : null}
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
        {kindLabel}
      </span>
      {dayLabel ? (
        <span className="text-on-surface-variant text-[9px] font-medium tabular-nums">
          {dayLabel}
        </span>
      ) : null}
    </div>
  );
}
