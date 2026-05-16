/** Comment do app gửi qua Playwright — mảng trên cột ``comment`` / ``Comment``. */

export const APP_COMMENT_DAY_KEY = "ngày comment" as const;

export type AppCommentEntry = {
  comment_content: string;
  [APP_COMMENT_DAY_KEY]: string;
};

export function appCommentContent(entry: AppCommentEntry): string {
  return entry.comment_content.trim();
}

export function appCommentDay(entry: AppCommentEntry): string {
  return entry[APP_COMMENT_DAY_KEY].trim();
}

function normalizeEntry(raw: unknown): AppCommentEntry | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const comment = String(
    o.comment_content ?? o.commentContent ?? o.comment ?? "",
  ).trim();
  const day = String(
    o[APP_COMMENT_DAY_KEY] ??
      o.ngay_comment ??
      o.day_comment ??
      o.dayComment ??
      "",
  ).trim();
  if (!comment || !day) return null;
  return {
    comment_content: comment,
    [APP_COMMENT_DAY_KEY]: day.slice(0, 10),
  };
}

/** Đọc mảng comment đã gửi từ bản ghi post (sheet/API). */
export function parseAppCommentsFromPost(
  post: Record<string, unknown>,
): AppCommentEntry[] {
  const keys = [
    "comments", // ← From API/Sheet (main field)
    "comment",
    "Comment",
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
          const out = j
            .map(normalizeEntry)
            .filter(Boolean) as AppCommentEntry[];
          if (out.length) return out;
        }
      } catch {
        /* bỏ qua chuỗi không phải JSON */
      }
    }
  }
  return [];
}

/** Ngày local ISO ``YYYY-MM-DD`` (khớp ``ngày comment`` backend). */
export function isoDayLocal(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Patch UI sau khi comment thành công — ghi mảng ``comment`` / ``Comment``. */
export function buildSheetCommentPatch(
  comments: AppCommentEntry[],
): Record<string, AppCommentEntry[]> {
  return {
    comment: comments,
    Comment: comments,
  };
}
