/**
 * @deprecated Use @/lib/LinkedIn-parse-group-urls-bulk instead
 */

/** Trích mọi URL nhóm LinkedIn từ text (dòng mới, phẩy, dính liền…). */

const GROUP_URL_RE = /https:\/\/(www\.)?linkedin\.com\/groups\/\d+\/?/gi;

const SINGLE_LINE_GROUP_URL =
  /^https:\/\/(www\.)?linkedin\.com\/groups\/\d+\/?$/i;

export function parseGroupUrlsFromBulkInput(input: string): string[] {
  const raw = input.trim();
  if (!raw) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  GROUP_URL_RE.lastIndex = 0;
  for (const m of raw.matchAll(GROUP_URL_RE)) {
    let u = m[0].trim();
    if (!u.endsWith("/")) u += "/";
    const key = u.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(u);
    }
  }
  return out;
}

/**
 * Khi blur: nếu dòng cuối là một URL nhóm (chưa có dấu phẩy sau URL) thì thêm `,` và xuống dòng
 * để dễ dán URL tiếp theo.
 */
export function appendCommaNewlineAfterTrailingGroupUrl(text: string): string {
  const noTrailSpace = text.replace(/[ \t\u00a0]+$/g, "");
  if (!noTrailSpace) return text;
  const lines = noTrailSpace.split("\n");
  const i = lines.length - 1;
  const lastRaw = lines[i] ?? "";
  const lastTrim = lastRaw.trimEnd();
  const withoutComma = lastTrim.replace(/,\s*$/, "");
  if (!SINGLE_LINE_GROUP_URL.test(withoutComma)) return text;
  if (lastTrim.endsWith(",")) {
    return noTrailSpace.endsWith("\n") ? text : `${noTrailSpace}\n`;
  }
  const lastNew = `${withoutComma},`;
  const joined = [...lines.slice(0, i), lastNew].join("\n");
  return joined.endsWith("\n") ? joined : `${joined}\n`;
}
