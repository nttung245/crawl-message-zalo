import { MaterialIcon, type MaterialSymbolName } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { PostLinkedInReactionKind } from "@/types/api";

/** Thứ tự hiển thị giống thanh reaction LinkedIn (trái → phải). */
export const REACTION_TOOLBAR_ORDER: readonly PostLinkedInReactionKind[] = [
  "like",
  "celebrate",
  "support",
  "love",
  "insightful",
  "funny",
] as const;

/** Icon Material Symbols Outlined — cùng style với nút «Nhóm LinkedIn» / «Xem bài». */
const REACTION_MATERIAL_ICON: Record<
  PostLinkedInReactionKind,
  MaterialSymbolName
> = {
  like: "thumb_up",
  celebrate: "celebration",
  support: "volunteer_activism",
  love: "favorite",
  insightful: "lightbulb",
  funny: "sentiment_very_satisfied",
};

export function reactionToolbarLabelVi(kind: PostLinkedInReactionKind): string {
  const labels: Record<PostLinkedInReactionKind, string> = {
    like: "Like",
    celebrate: "Celebrate",
    support: "Support",
    love: "Love",
    insightful: "Insightful",
    funny: "Funny",
  };
  return labels[kind];
}

/** Nhãn «đã tương tác» tiếng Việt (chip / bảng). */
export function reactionDoneLabelVi(kind: PostLinkedInReactionKind): string {
  const labels: Record<PostLinkedInReactionKind, string> = {
    like: "Đã Like",
    celebrate: "Đã chúc mừng",
    support: "Đã cổ vũ",
    love: "Đã Yêu thích",
    insightful: "Đã Thấy hay",
    funny: "Đã Hài hước",
  };
  return labels[kind];
}

const _KIND_ALIASES: Record<string, PostLinkedInReactionKind> = {
  like: "like",
  love: "love",
  celebrate: "celebrate",
  support: "support",
  insightful: "insightful",
  funny: "funny",
  "chúc mừng": "celebrate",
  "chuc mung": "celebrate",
  "yêu thích": "love",
  "yeu thich": "love",
  "cổ vũ": "support",
  "co vu": "support",
  "thấy hay": "insightful",
  "thay hay": "insightful",
  "hài hước": "funny",
  "hai huoc": "funny",
};

/** Chuẩn hoá token sheet/API → kind reaction (hoặc null). */
export function parseReactionKindFromSheet(
  raw: string,
): PostLinkedInReactionKind | null {
  let t = raw.trim().toLowerCase().normalize("NFC");
  if (!t) return null;
  t = t.replace(/^(đã|da)\s+/u, "").trim();
  const direct = _KIND_ALIASES[t];
  if (direct) return direct;
  const nospace = t.replace(/\s+/g, "");
  return _KIND_ALIASES[nospace] ?? null;
}

/**
 * Icon reaction — Material Symbols Outlined (đồng bộ nút border-primary trong modal).
 * ``variant="mono"``: kế thừa ``currentColor`` (chip / nền trung tính).
 * ``variant="color"``: ép ``text-primary`` khi cần nổi teal độc lập.
 */
export function ReactionToolbarGlyph({
  kind,
  variant = "color",
  emphasis = false,
  className,
}: {
  kind: PostLinkedInReactionKind;
  variant?: "color" | "mono";
  emphasis?: boolean;
  className?: string;
}) {
  const name = REACTION_MATERIAL_ICON[kind];
  return (
    <MaterialIcon
      name={name}
      className={cn(
        "inline-block shrink-0 align-middle leading-none transition-transform duration-200 ease-out will-change-transform",
        emphasis ? "scale-110" : undefined,
        variant === "color" ? "text-primary" : "text-current",
        className,
      )}
    />
  );
}
