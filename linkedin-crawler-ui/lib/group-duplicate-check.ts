/**
 * @deprecated Use @/lib/LinkedIn-group-duplicate-check instead
 */
import type { ManagedGroupRow } from "@/lib/LinkedIn-n8n-groups-normalize";

/** Khớp logic ``_group_url_match_key`` trên backend (normalize linkedin path + lowercase). */
export function groupUrlMatchKey(url: string): string {
  const t = url.trim();
  if (!t) return "";
  let u = t;
  if (!/^https?:\/\//i.test(u)) u = `https://${u}`;
  u = u.replace(/^http:\/\//i, "https://");
  try {
    const x = new URL(u);
    if (!x.hostname.toLowerCase().endsWith("linkedin.com")) {
      return u.toLowerCase().replace(/\/+$/, "");
    }
    const path = `${(x.pathname || "").replace(/\/+$/, "")}/`;
    return `${x.protocol}//${x.host}${path}`.toLowerCase().replace(/\/+$/, "");
  } catch {
    return u.toLowerCase().replace(/\/+$/, "");
  }
}

export function findDuplicateManagedGroup(
  rows: ManagedGroupRow[],
  url: string,
  ownerEmail: string,
): ManagedGroupRow | undefined {
  const owner = ownerEmail.trim().toLowerCase();
  if (!owner) return undefined;
  const k = groupUrlMatchKey(url);
  return rows.find((r) => {
    if (groupUrlMatchKey(r.url_group) !== k) return false;
    return (r.email || "").trim().toLowerCase() === owner;
  });
}

export function duplicateManagedGroupMessage(row: ManagedGroupRow): string {
  const name = row.name_group?.trim() || "—";
  const url = row.url_group?.trim() || "—";
  return `Nhóm: ${name} url:${url} đã có trong danh sách!`;
}
