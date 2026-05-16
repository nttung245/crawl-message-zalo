import type { PostLinkedInReactionKind } from "@/types/api";
import {
  isoDayLocal,
  parseAppCommentsFromPost,
} from "@/lib/LinkedIn-appComments";

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

export interface SheetReactionCell {
  type: PostLinkedInReactionKind;
  triggered_at: string;
  day_trigger: string;
}

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

const REACTION_CELL_TYPE_KEYS = [
  "type",
  "kind",
  "reaction",
  "reaction_type",
  "Reaction_type",
] as const;

const REACTION_CELL_DAY_KEYS = [
  "day_trigger",
  "dayTrigger",
  "triggered_at",
  "triggeredAt",
] as const;

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

function asReactionRecord(value: unknown): Record<string, unknown> | null {
  let current: unknown = value;
  for (let depth = 0; depth < 3; depth += 1) {
    if (current == null || isEmptySheetCell(current)) return null;
    if (typeof current === "object" && !Array.isArray(current)) {
      return current as Record<string, unknown>;
    }
    if (typeof current !== "string") return null;
    const text = current.trim();
    if (!text.startsWith("{")) return null;
    try {
      current = JSON.parse(text) as unknown;
    } catch {
      return null;
    }
  }
  return null;
}

function reactionTypeTokenFromCell(value: unknown): string {
  const record = asReactionRecord(value);
  if (record) {
    return pickFirstRaw(record, REACTION_CELL_TYPE_KEYS);
  }
  if (value == null || isEmptySheetCell(value)) return "";
  return String(value).trim();
}

function reactionTriggerDayFromCell(value: unknown): string {
  const record = asReactionRecord(value);
  if (!record) return "";
  const raw = pickFirstRaw(record, REACTION_CELL_DAY_KEYS);
  return raw.slice(0, 10);
}

export function formatSheetInteractionDayLabelVi(day: string): string {
  const d = day.trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return day.trim();
  const [y, m, dayNum] = d.split("-");
  return `${dayNum}/${m}/${y}`;
}

/** Gỡ reaction trên sheet/UI — giữ chuỗi rỗng, không dùng null. */
export function buildSheetReactionClearPatch(): Record<string, string> {
  return {
    reaction: "",
    Reaction: "",
  };
}

/** Object ``reaction`` gửi sheet / merge UI sau khi automation thành công. */
export function buildSheetReactionCell(
  kind: PostLinkedInReactionKind,
): SheetReactionCell {
  const triggered_at = new Date().toISOString();
  return {
    type: kind,
    triggered_at,
    day_trigger: isoDayLocal(),
  };
}

/** Đọc object hoặc chuỗi reaction từ sheet/API. */
export function parseSheetReaction(post: Record<string, unknown>): {
  kind: PostLinkedInReactionKind | null;
  triggerDay: string;
} {
  let kind: PostLinkedInReactionKind | null = null;
  let triggerDay = "";

  for (const k of SHEET_REACTION_KEYS) {
    if (!(k in post)) continue;
    const raw = post[k];
    if (isEmptySheetCell(raw)) continue;
    const typeToken = reactionTypeTokenFromCell(raw);
    const parsedKind = parseReactionKindFromSheet(typeToken);
    if (parsedKind) kind = parsedKind;
    const day = reactionTriggerDayFromCell(raw);
    if (day) triggerDay = day;
    if (kind && triggerDay) break;
  }

  if (!triggerDay) {
    const fromPost = pickFirstRaw(post, REACTION_CELL_DAY_KEYS);
    if (fromPost) triggerDay = fromPost.slice(0, 10);
  }

  return { kind, triggerDay };
}

/** Raw token loại reaction (chuỗi) — tương thích dữ liệu cũ. */
export function sheetReactionRaw(post: Record<string, unknown>): string {
  const { kind } = parseSheetReaction(post);
  return kind ?? "";
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
  const { kind, triggerDay } = parseSheetReaction(post);
  if (!kind) return "Chưa tương tác";
  const label = reactionDoneLabelVi(kind);
  if (!triggerDay) return label;
  const dayLabel = formatSheetInteractionDayLabelVi(triggerDay);
  return dayLabel ? `${label} · ${dayLabel}` : label;
}

/** Số comment automation đã gửi qua app (ô ``comment`` / ``Comment``). */
export function countAppCommentsFromPost(
  post: Record<string, unknown>,
): number {
  return parseAppCommentsFromPost(post).length;
}

/** Nhãn automation «đã / chưa bình luận» (theo ô ``comment`` hoặc alias). */
export function formatSheetCommentAutomationLabelVi(
  post: Record<string, unknown>,
): string {
  const count = countAppCommentsFromPost(post);
  if (count === 0) return "Chưa bình luận";
  return `Đã có ${count.toLocaleString("vi-VN")} bình luận trên bài viết này`;
}
