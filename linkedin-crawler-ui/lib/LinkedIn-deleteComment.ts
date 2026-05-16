/**
 * LinkedIn comment deletion service.
 * Calls POST /linkedin/post/comment/delete API endpoint.
 */

import type { PostLinkedInCommentDeleteResponse } from "@/types/api";

export interface DeleteLinkedInCommentInput {
  profileSlug: string; // e.g., "nmhoang-dev"
  postUrl: string; // LinkedIn post URL
  commentText: string; // Comment content to delete
  emailCrawl: string; // Crawl account email
  idSessionCrawl: string; // Session ID
  rowNumber: number; // Row number in sheet
  sessionId?: string; // Playwright session ID
  email?: string; // Email for Playwright
  postToWebhook?: boolean; // Whether to sync to sheet
  sheetRow?: Record<string, unknown>; // Full row data
  maxScroll?: number; // Max scroll attempts (1-20, default 8)
  timeoutMs?: number; // Timeout in ms (30000-300000, default 120000)
}

/**
 * Delete a comment from LinkedIn post directly.
 * Optimized: Goes directly to post URL instead of recent-activity page.
 * After successful deletion, syncs changes back to Google Sheet.
 *
 * @param input Delete comment parameters (includes postUrl for direct access)
 * @returns Response from API
 * @throws Error if API call fails
 */
export async function deleteLinkedInComment(
  input: DeleteLinkedInCommentInput,
): Promise<PostLinkedInCommentDeleteResponse> {
  const payload = {
    profile_slug: input.profileSlug,
    post_url: input.postUrl,
    comment_text: input.commentText,
    Email_crawl: input.emailCrawl,
    ID_session_crawl: input.idSessionCrawl,
    row_number: input.rowNumber,
    session_id: input.sessionId,
    email: input.email,
    post_to_webhook: input.postToWebhook ?? true,
    sheet_row: input.sheetRow,
    max_scroll: input.maxScroll ?? 8,
    timeout_ms: input.timeoutMs ?? 120000,
  };

  const response = await fetch("/api/linkedin/post/comment/delete", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Delete comment API error: ${response.status} - ${errorText}`,
    );
  }

  return response.json();
}

/**
 * Extract profile slug from LinkedIn profile URL.
 * Handles various URL formats: full URL, path-only, etc.
 */
export function extractProfileSlugFromUrl(linkedinUrl: string): string {
  if (!linkedinUrl) return "";

  try {
    const url = new URL(
      linkedinUrl.startsWith("http")
        ? linkedinUrl
        : `https://linkedin.com${linkedinUrl}`,
    );
    const pathParts = url.pathname.split("/").filter(Boolean);

    // Profile URL format: /in/{slug}/... or just /in/{slug}
    const inIndex = pathParts.indexOf("in");
    if (inIndex >= 0 && inIndex + 1 < pathParts.length) {
      return pathParts[inIndex + 1];
    }

    return "";
  } catch {
    // Fallback: extract from path-like string
    const match = linkedinUrl.match(/\/in\/([^/?]+)/);
    return match ? match[1] : "";
  }
}
