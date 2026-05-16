/**
 * @deprecated Use @/lib/LinkedIn-postReactionWebhookBody instead
 */

/**
 * ## Body webhook reaction — ``N8N_WEBHOOK_REACTION`` / ``N8N_WEBHOOK_POST_REACTION``
 *
 * Luồng backend: app reaction → Playwright → get-all (n8n) → parse dòng khớp **url + email**
 * (gộp luôn dòng trigger nếu chưa có) → POST **chỉ một mảng JSON** ``[ {...}, ... ]``.
 *
 * Mỗi phần tử: key sheet gốc + slug tiếng Việt không dấu, metric chuẩn, ``row_number``/``STT``.
 * ``reaction`` / ``Reaction`` là object:
 * ``{ type, triggered_at, day_trigger }``.
 *
 * Ví dụ một phần tử (rút gọn):
 *
 * ```json
 * {
 *   "Tên nhóm": "…",
 *   "tennhom": "…",
 *   "URL_Bài_Viết": "https://www.linkedin.com/feed/update/urn:li:activity:…/",
 *   "urlbaiviet": "https://www.linkedin.com/feed/update/urn:li:activity:…/",
 *   "Email_crawl": "user@gmail.com",
 *   "ID_session_crawl": "user_1234567890",
 *   "row_number": 3,
 *   "rownumber": 3,
 *   "STT": 3,
 *   "reaction": {
 *     "type": "like",
 *     "triggered_at": "2026-05-11T06:35:12.456Z",
 *     "day_trigger": "2026-05-11"
 *   },
 *   "Reaction": {
 *     "type": "like",
 *     "triggered_at": "2026-05-11T06:35:12.456Z",
 *     "day_trigger": "2026-05-11"
 *   },
 *   "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:…/",
 *   "final_url": "https://www.linkedin.com/feed/update/urn:li:activity:…/",
 *   "resolved_playwright_session_id": "storage-state-email…"
 * }
 * ```
 */
export type PostReactionWebhookRow = Record<string, unknown> & {
  reaction?: {
    type: string;
    triggered_at: string;
    day_trigger: string;
  };
};
