/** Comment do app gửi qua Playwright — lưu mảng { comment, day_comment }. */

export type AppCommentEntry = {
  comment: string;
  day_comment: string;
};

function normalizeEntry(raw: unknown): AppCommentEntry | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const comment = String(o.comment ?? "").trim();
  const day = String(o.day_comment ?? o.dayComment ?? "").trim();
  if (!comment || !day) return null;
  return { comment, day_comment: day };
}

/** Đọc mảng comment đã gửi từ bản ghi post (sheet/API). */
export function parseAppCommentsFromPost(
  post: Record<string, unknown>,
): AppCommentEntry[] {
  const keys = [
    "app_comments",
    "linkedin_app_comments",
    "app_comments_json",
    "comments_app",
  ];
  for (const k of keys) {
    const v = post[k];
    if (Array.isArray(v)) {
      return v.map(normalizeEntry).filter(Boolean) as AppCommentEntry[];
    }
    if (typeof v === "string" && v.trim()) {
      try {
        const j = JSON.parse(v) as unknown;
        if (Array.isArray(j)) {
          const out = j.map(normalizeEntry).filter(Boolean) as AppCommentEntry[];
          if (out.length) return out;
        }
      } catch {
        /* bỏ qua chuỗi không phải JSON */
      }
    }
  }
  return [];
}

/** Ngày local ISO ``YYYY-MM-DD`` (khớp ``day_comment`` backend). */
export function isoDayLocal(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
