/**
 * LinkedIn comment editing service.
 * Calls POST /linkedin/post/comment/edit API endpoint.
 */

import type { PostLinkedInCommentEditResponse } from "@/types/api";

export interface EditLinkedInCommentInput {
  profileSlug: string; // e.g., "nmhoang-dev"
  postUrl: string; // LinkedIn post URL
  commentText: string; // Old comment content (to find)
  newCommentText: string; // New comment content
  emailCrawl: string; // Crawl account email
  idSessionCrawl: string; // Session ID
  rowNumber: number; // Row number in sheet
  sessionId?: string; // Playwright session ID
  email?: string; // Email for Playwright
  postToWebhook?: boolean; // Whether to sync to sheet
  sheetRow?: Record<string, unknown>; // Full row data
  timeoutMs?: number; // Timeout in ms (30000-300000, default 120000)
}

/**
 * Edit a comment on LinkedIn post detail.
 * After successful edit, syncs changes back to Google Sheet.
 *
 * @param input Edit comment parameters (includes postUrl for direct access)
 * @returns Response from API
 * @throws Error if API call fails
 */
export async function editLinkedInComment(
  input: EditLinkedInCommentInput,
): Promise<PostLinkedInCommentEditResponse> {
  const payload = {
    profile_slug: input.profileSlug,
    post_url: input.postUrl,
    comment_text: input.commentText,
    new_comment_text: input.newCommentText,
    Email_crawl: input.emailCrawl,
    ID_session_crawl: input.idSessionCrawl,
    row_number: input.rowNumber,
    session_id: input.sessionId,
    email: input.email,
    post_to_webhook: input.postToWebhook ?? true,
    sheet_row: input.sheetRow,
    timeout_ms: input.timeoutMs ?? 120000,
  };

  const response = await fetch("/api/linkedin/post/comment/edit", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Edit comment API error: ${response.status} - ${errorText}`,
    );
  }

  return response.json();
}
