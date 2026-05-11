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

/** Các key thường dùng cho số dòng sheet / STT. */
const ROW_NUMBER_KEYS = [
  "row_number",
  "rowNumber",
  "STT",
  "stt",
  "Stt",
] as const;

/** Có số dòng thực sự (>0) từ sheet/webhook — không tính ô trống / 0. */
export function hasMeaningfulRowNumber(record: Record<string, unknown>): boolean {
  for (const k of ROW_NUMBER_KEYS) {
    if (!(k in record)) continue;
    const v = record[k];
    if (v == null) continue;
    if (typeof v === "string" && !v.trim()) continue;
    const n = typeof v === "number" ? v : Number(String(v).trim());
    if (!Number.isNaN(n) && n > 0) return true;
  }
  return false;
}

/** ``row_number`` / ``STT`` … đúng như bản ghi từ API (get-all-posts); không ép số cột «#». Chỉ fallback khi không có số ≥ 1. */
export function pickPositiveRowNumberFromPost(
  record: Record<string, unknown>,
): number | undefined {
  for (const k of ROW_NUMBER_KEYS) {
    if (!(k in record)) continue;
    const v = record[k];
    if (v == null) continue;
    if (typeof v === "string" && !v.trim()) continue;
    const n = typeof v === "number" ? v : Number(String(v).trim());
    if (!Number.isNaN(n) && n >= 1) return Math.trunc(n);
  }
  return undefined;
}

/**
 * Khi sheet/n8n không trả ``row_number``/``STT``, gán fallback là **thứ tự bài trong phiên** (1…n)
 * để UI và ``sheet_row`` gửi webhook không bị trống.
 *
 * Lưu ý: Đây là ordinal trong phiên, không phải tự động bằng **số hàng Google Sheet** —
 * để khớp đúng hàng sheet cần map STT trong workflow n8n.
 */
export function enrichPostRowNumberIfMissing(
  record: Record<string, unknown>,
  fallbackOrdinalInSession: number,
): Record<string, unknown> {
  if (hasMeaningfulRowNumber(record)) return record;
  return {
    ...record,
    row_number: fallbackOrdinalInSession,
    rowNumber: fallbackOrdinalInSession,
    STT: fallbackOrdinalInSession,
    stt: fallbackOrdinalInSession,
  };
}

function isEmptySheetCell(v: unknown): boolean {
  if (v == null) return true;
  if (typeof v === "string" && !v.trim()) return true;
  return false;
}

/**
 * Gộp meta phiên (email, id phiên, nhóm, **tổng số bài trong phiên**) vào bản ghi bài trước khi gửi ``sheet_row``.
 *
 * - Email / nhóm / id phiên: chỉ điền khi ô trên dòng đang trống (không ghi đè ``Ngày``, nội dung, …).
 * - ``posts_count`` và cột «Tổng số bài lấy được mỗi lần cào»: **luôn** gán theo bảng phiên (khớp UI).
 * - ``row_number`` / ``STT``: giữ nguyên như object ``post`` (dữ liệu GET); không ghi đè ordinal bảng.
 */
export function buildReactionWebhookSheetRow(
  post: Record<string, unknown>,
  session: CrawlSessionGroup,
): Record<string, unknown> {
  const out = { ...post };
  const sid = session.id_session_crawl?.trim();
  const ec = session.email_crawl?.trim();
  const gu = session.group_url?.trim();
  const gn = session.group_name?.trim();

  const fill = (key: string, val: string | undefined) => {
    if (!val) return;
    if (!isEmptySheetCell(out[key])) return;
    out[key] = val;
  };

  fill("ID_session_crawl", sid);
  fill("id_session_crawl", sid);
  fill("Email_crawl", ec);
  fill("email_crawl", ec);
  fill("group_url", gu);
  fill("groupUrl", gu);
  fill("URL_Nhóm", gu);
  fill("URL_nhom", gu);
  fill("group_name", gn);
  fill("groupName", gn);
  fill("Tên nhóm", gn);

  const pc = session.posts_count;
  if (typeof pc === "number" && Number.isFinite(pc) && pc >= 0) {
    out["posts_count"] = pc;
    out["Tổng số bài lấy được mỗi lần cào"] = pc;
  }

  return out;
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
