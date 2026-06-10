function normalizeUrl(value?: string): string | undefined {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  return trimmed.replace(/\/+$/, "");
}

export const API_BASE_URL =
  normalizeUrl(process.env.NEXT_PUBLIC_ZALO_API_BASE_URL) ??
  normalizeUrl(process.env.NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL) ??
  "http://localhost:8000";

export const API_KEY =
  process.env.NEXT_PUBLIC_ZALO_API_KEY ??
  process.env.NEXT_PUBLIC_LINKEDIN_CRAWLER_API_KEY ??
  "";
