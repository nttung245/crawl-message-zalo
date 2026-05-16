import { pickStr } from "@/components/features/linkedin/dashboard/LinkedIn-n8n-sheet-helpers";
import { getKpiByEmail } from "@/services/linkedinCrawlerService";

function slugFromRecord(record: Record<string, unknown> | undefined): string {
  if (!record) return "";
  const slug = pickStr(record, [
    "profile_slug",
    "profileSlug",
    "slug",
    "Profile_slug",
  ])
    .trim()
    .toLowerCase();
  if (!slug || slug === "me") return "";
  return slug;
}

/**
 * Lấy profile_slug từ dòng sheet (post/session) hoặc KPI get-by-email — không mở Playwright /in/me.
 */
export async function resolveProfileSlugFromSheetForEmail(
  crawlEmail: string,
  hints?: {
    post?: Record<string, unknown>;
    session?: Record<string, unknown>;
  },
): Promise<string> {
  for (const record of [hints?.post, hints?.session]) {
    const fromRow = slugFromRecord(record);
    if (fromRow) return fromRow;
  }

  const email = crawlEmail.trim();
  if (!email.includes("@")) {
    throw new Error("Email_crawl không hợp lệ để tra profile trên sheet.");
  }

  const res = await getKpiByEmail({ email });
  if (!res.success || !res.data?.length) {
    throw new Error(
      res.message || "Không tìm thấy profile trên sheet (kpi/get-by-email).",
    );
  }

  const norm = email.toLowerCase();
  const row =
    res.data.find((r) => (r.email || "").trim().toLowerCase() === norm) ??
    res.data[0];
  const slug = (row.profile_slug || "").trim().toLowerCase();
  if (!slug || slug === "me") {
    throw new Error("Sheet chưa có profile_slug cho email cào này.");
  }
  return slug;
}
