import type { CrawlSessionGroup } from "@/types/api";

/**
 * Gộp nhiều mảng phiên (ví dụ mỗi lần gọi get-all-posts với một ``email`` khác nhau),
 * bỏ trùng theo ``email_crawl`` + ``id_session_crawl``.
 */
export function mergeCrawlSessionGroups(
  chunks: readonly (readonly CrawlSessionGroup[] | null | undefined)[],
): CrawlSessionGroup[] {
  const byKey = new Map<string, CrawlSessionGroup>();
  for (const chunk of chunks) {
    if (!chunk?.length) continue;
    for (const s of chunk) {
      const em = String(s.email_crawl ?? "")
        .trim()
        .toLowerCase();
      const id = String(s.id_session_crawl ?? "").trim();
      const key = id ? `${em}::${id}` : `${em}::noid:${byKey.size}`;
      if (!byKey.has(key)) byKey.set(key, s);
    }
  }
  return [...byKey.values()];
}
