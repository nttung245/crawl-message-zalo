export const API_BASE_URL =
  process.env.NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL?.replace(/\/+$/, "") ??
  "http://localhost:8000";

export const API_KEY = process.env.NEXT_PUBLIC_LINKEDIN_CRAWLER_API_KEY ?? "";

export const ZALO_API_BASE_URL =
  process.env.NEXT_PUBLIC_ZALO_API_BASE_URL?.replace(/\/+$/, "") ??
  process.env.NEXT_PUBLIC_ZALO_CRAWLER_API_URL?.replace(/\/+$/, "") ??
  API_BASE_URL;

export const ZALO_API_KEY =
  process.env.NEXT_PUBLIC_ZALO_API_KEY ??
  process.env.NEXT_PUBLIC_ZALO_CRAWLER_API_KEY ??
  "";
