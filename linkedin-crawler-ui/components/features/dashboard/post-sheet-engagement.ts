import {
  parseReactionKindFromSheet,
  reactionDoneLabelVi,
} from "./linkedin-reaction-icons";

/** Đọc trạng thái tương tác / bình luận automation từ dòng sheet/API (không dùng Số comment LinkedIn). */

const SHEET_REACTION_KEYS = [
  "reaction",
  "Reaction",
  "reaction_type",
  "Reaction_type",
  "loại_tương_tác",
  "Loại tương tác",
  "tuong_tac",
  "Tuong_tac",
] as const;

/** Cột “đã comment automation” — có `comment` để khớp yêu cầu null / không null. */
const SHEET_COMMENT_AUTOMATION_KEYS = [
  "comment",
  "Comment",
  "comment_sheet",
  "Comment_sheet",
  "da_comment",
  "Da_comment",
  "Đã bình luận",
  "ghi_chu_binh_luan",
  "Ghi_chú_bình_luận",
] as const;

function isEmptySheetCell(value: unknown): boolean {
  if (value == null) return true;
  if (typeof value === "string") {
    const t = value.trim().toLowerCase();
    return (
      t === "" ||
      t === "null" ||
      t === "undefined" ||
      t === "false" ||
      t === "0" ||
      t === "no" ||
      t === "không"
    );
  }
  if (typeof value === "number") return value === 0 || Number.isNaN(value);
  if (typeof value === "boolean") return !value;
  return false;
}

/** Ẩn các key meta khỏi khối «đầy đủ trường» trong modal chi tiết. */
export const ENGAGEMENT_SHEET_FIELD_KEYS = new Set<string>([
  ...SHEET_REACTION_KEYS,
  ...SHEET_COMMENT_AUTOMATION_KEYS,
]);

function pickFirstRaw(
  post: Record<string, unknown>,
  keys: readonly string[],
): string {
  for (const k of keys) {
    if (!(k in post)) continue;
    const v = post[k];
    if (isEmptySheetCell(v)) continue;
    return String(v).trim();
  }
  return "";
}

/** Raw reaction token từ sheet (vd. `like`, `celebrate`). */
export function sheetReactionRaw(post: Record<string, unknown>): string {
  return pickFirstRaw(post, SHEET_REACTION_KEYS);
}

/** Raw ô automation comment (text hoặc cờ). */
export function sheetCommentAutomationRaw(
  post: Record<string, unknown>,
): string {
  return pickFirstRaw(post, SHEET_COMMENT_AUTOMATION_KEYS);
}

/** Nhãn một dòng cho cột «Tương tác» trong bảng phiên / modal. */
export function formatSheetInteractionLabelVi(
  post: Record<string, unknown>,
): string {
  const raw = sheetReactionRaw(post);
  if (!raw) return "Chưa tương tác";
  const lower = raw.toLowerCase().normalize("NFC");
  if (lower.startsWith("đã ") || lower.startsWith("da ")) {
    const parsed = parseReactionKindFromSheet(raw);
    if (parsed) return reactionDoneLabelVi(parsed);
    return raw.trim();
  }
  const parsed = parseReactionKindFromSheet(raw);
  if (parsed) return reactionDoneLabelVi(parsed);
  return `Đã ${raw}`;
}

/** Nhãn automation «đã / chưa bình luận» (theo ô ``comment`` hoặc alias). */
export function formatSheetCommentAutomationLabelVi(
  post: Record<string, unknown>,
): string {
  const raw = sheetCommentAutomationRaw(post);
  if (!raw) return "Chưa bình luận";
  return "Đã bình luận";
}
