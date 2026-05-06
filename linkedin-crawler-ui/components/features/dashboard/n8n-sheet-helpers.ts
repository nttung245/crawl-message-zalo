import type { CrawlSessionGroup } from "@/types/api";

/** Giá trị string từ bản ghi sheet/webhook (key thường gặp). */
export function pickStr(
  record: Record<string, unknown>,
  keys: string[],
): string {
  for (const k of keys) {
    if (!(k in record)) continue;
    const v = record[k];
    if (v == null) continue;
    const s = String(v).trim();
    if (s) return s;
  }
  return "";
}

export function pickNum(
  record: Record<string, unknown>,
  keys: string[],
): number {
  for (const k of keys) {
    if (!(k in record)) continue;
    const v = record[k];
    if (typeof v === "number" && !Number.isNaN(v)) return v;
    if (typeof v === "string" && v.trim()) {
      const n = Number(v);
      if (!Number.isNaN(n)) return n;
    }
  }
  return 0;
}

export function shortenSessionId(id: string, head = 14, tail = 8): string {
  if (id.length <= head + tail + 3) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

/** Ngày đại diện của phiên (max ``Ngày`` / ``date`` trong các bài). */
export function sessionLatestDateLabel(session: CrawlSessionGroup): string {
  let best = "";
  for (const p of session.posts) {
    const d = pickStr(p, ["Ngày", "date", "targetDate"])
      .slice(0, 10)
      .trim();
    if (d && d > best) best = d;
    const raw = pickStr(p, ["Đăng vào", "posted_at", "created_at"]);
    if (raw.length >= 10) {
      const head = raw.slice(0, 10);
      if (head > best) best = head;
    }
  }
  return best || "—";
}

export function formatCellValue(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object")
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  return String(v);
}

export function sortedRecordEntries(
  record: Record<string, unknown>,
): [string, unknown][] {
  return Object.entries(record).sort(([a], [b]) =>
    a.localeCompare(b, "vi", { sensitivity: "base" }),
  );
}
