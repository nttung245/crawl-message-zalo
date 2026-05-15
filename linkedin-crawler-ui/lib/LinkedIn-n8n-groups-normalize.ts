import { deriveGroupDisplayName } from "@/components/features/dashboard/dashboard-helpers";

/** Một dòng nhóm sau khi chuẩn hóa từ JSON n8n. */
export interface ManagedGroupRow {
  row_number: number | null;
  url_group: string;
  name_group: string;
  email: string;
  member: number;
  type: string;
}

function pickStr(obj: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return "";
}

function pickNum(obj: Record<string, unknown>, keys: string[]): number {
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === "number" && !Number.isNaN(v))
      return Math.max(0, Math.trunc(v));
    if (typeof v === "string" && v.trim()) {
      const n = Number(String(v).replace(/\s/g, "").replace(/,/g, ""));
      if (!Number.isNaN(n)) return Math.max(0, Math.trunc(n));
    }
  }
  return 0;
}

function rowFromUnknown(item: unknown): ManagedGroupRow | null {
  if (!item || typeof item !== "object") return null;
  const o = item as Record<string, unknown>;
  const rowRaw = pickNum(o, ["row_number", "rowNumber", "stt", "STT"]);
  const row_number = rowRaw > 0 ? rowRaw : null;
  const url = pickStr(o, [
    "url_group",
    "URL_Nhóm",
    "url_nhom",
    "group_url",
    "groupUrl",
    "link",
    "Link nhóm",
    "Link",
  ]);
  if (!url) return null;
  const name =
    pickStr(o, [
      "name_group",
      "Tên nhóm",
      "ten_nhom",
      "group_name",
      "groupName",
      "name",
    ]) || deriveGroupDisplayName(url);
  const member = pickNum(o, [
    "member",
    "members",
    "Member",
    "so_thanh_vien",
    "count",
    "Số thành viên",
  ]);
  const email = pickStr(o, [
    "email",
    "Email_crawl",
    "email_crawl",
    "userEmail",
  ]);
  const type = pickStr(o, [
    "type",
    "Loại nhóm",
    "loai_nhom",
    "intent",
  ]);
  return { row_number, url_group: url, name_group: name, email, member, type };
}

/**
 * Gỡ bố cục phổ biến từ body JSON n8n (mảng, hoặc `{ data: [] }`, `{ groups: [] }`, …).
 */
export function normalizeN8nGroupsList(parsed: unknown): ManagedGroupRow[] {
  if (parsed == null) return [];
  if (Array.isArray(parsed)) {
    return parsed
      .map(rowFromUnknown)
      .filter((x): x is ManagedGroupRow => x != null);
  }
  if (typeof parsed === "object") {
    const o = parsed as Record<string, unknown>;
    if (Array.isArray(o.groups)) {
      return normalizeN8nGroupsList(o.groups);
    }
    for (const key of [
      "data",
      "groups",
      "rows",
      "items",
      "results",
      "records",
    ]) {
      const arr = o[key];
      if (Array.isArray(arr)) return normalizeN8nGroupsList(arr);
    }
    const inner = o.data;
    if (inner != null && inner !== parsed) {
      return normalizeN8nGroupsList(inner);
    }
  }
  return [];
}
