/**
 * ## Body webhook reaction — URL trong crawler ``N8N_WEBHOOK_REACTION`` (fallback ``N8N_WEBHOOK_POST_REACTION``) (JSON một object phẳng)
 *
 * Backend ghép theo thứ tự:
 *
 * 1. Toàn bộ key/value trong ``sheet_row`` (payload POST `/linkedin/post/react`) — đúng các cột sheet của bạn.
 *    Với key có **tiếng Việt có dấu** hoặc có **khoảng trắng**, backend **thêm một key alias** thêm:
 *    bỏ dấu, chữ thường, viết liền chỉ ``[a-z0-9]`` (vd. ``Tên nhóm`` → ``tennhom``, ``URL_Bài_Viết`` → ``urlbaiviet``).
 *    Key ASCII một khối (vd. ``Email_crawl``) không sinh thêm alias.
 * 2. **Điền thêm** (UI): các ô phiên/nhóm còn trống trên dòng — ``Email_crawl``, ``ID_session_crawl``, ``URL_Nhóm``, ``Tên nhóm``, … lấy từ object phiên (không ghi đè ngày/nội dung đã có).
 * 3. Ghi đè luôn (ưu tiên cuối): ``Email_crawl``, ``ID_session_crawl``, ``row_number``, ``rownumber``, ``reaction``, ``post_url``, cộng meta automation:
 *    ``final_url`` (URL thực tế sau khi Playwright mở bài), ``resolved_playwright_session_id``, ``webhook_sent_at`` (ISO UTC).
 *
 * Toàn bộ object được **sanitize đệ quy** trước khi POST (datetime → ISO string, …) để không rơi field do kiểu không serialize được.
 *
 * **Metric LinkedIn trên dòng** (like, comment, báo cáo, điểm…): mọi cột có trong ``sheet_row`` vẫn giữ nguyên tên (vd. ``Số like``, ``Số comment``, ``Số báo cáo``, ``Điểm``) và slug không dấu (vd. ``solike``, ``socomment``, ``sobaocao``, ``diem``).
 * Backend **thêm** các key cố định (nếu đọc được số từ các cột đó): ``linkedin_like_count``, ``linkedin_comment_count``, ``linkedin_report_count``, ``post_score``, ``linkedin_post_score``.
 *
 * Khi ``reaction`` là ``like``, các ô like sheet (**``Số like``**, ``likes``, ``solike``, …) được **cộng thêm 1** trên payload trước khi POST (ước lượng lượt like sau khi bạn vừa like).
 *
 * **Tổng số bài trong phiên** (như cột «số bài / nhóm trong phiên» trên UI): UI luôn gửi ``posts_count`` + ``Tổng số bài lấy được mỗi lần cào`` + slug ``tongsobailayduocmoilancao``; backend bổ sung ``session_posts_count`` và ``total_posts_per_scrape``. Không nhầm với ``rownumber`` / ``row_number`` (đó là **STT dòng** bài đang reaction).
 *
 * ### Gợi ý cột để UI đọc trạng thái (song song với dữ liệu crawl)
 *
 * - **`reaction`**: giá trị tiếng Anh như ``like``, ``love``, ``celebrate``, ``support``, ``insightful``, ``funny`` — để trống hoặc ``null`` → hiển thị «Chưa tương tác». N8n sau workflow nên ghi lại đúng key này (hoặc alias xử lý trước khi trả về sheet).
 * - **`comment`**: text/ghi chú sau khi automation đã gửi bình luận (hoặc ``có`` / ``1``) — để trống hoặc ``null`` → «Chưa bình luận».
 *
 * **Không** dùng ``comment`` cho số lượt CMT LinkedIn — metric đó là ``Số comment`` / ``comments``.
 *
 * Ví dụ object sau merge (rút gọn — có cả key sheet gốc và slug tiếng Việt):
 *
 * ```json
 * {
 *   "Tên nhóm": "…",
 *   "tennhom": "…",
 *   "URL_Bài_Viết": "https://www.linkedin.com/feed/update/urn:li:activity:…/",
 *   "urlbaiviet": "https://www.linkedin.com/feed/update/urn:li:activity:…/",
 *   "Nội dung": "…",
 *   "noidung": "…",
 *   "Email_crawl": "user@gmail.com",
 *   "ID_session_crawl": "user_1234567890",
 *   "Số like": 127,
 *   "solike": 127,
 *   "linkedin_like_count": 127,
 *   "Số comment": 43,
 *   "socomment": 43,
 *   "linkedin_comment_count": 43,
 *   "Số báo cáo": 1,
 *   "sobaocao": 1,
 *   "linkedin_report_count": 1,
 *   "Điểm": 88,
 *   "diem": 88,
 *   "post_score": 88,
 *   "linkedin_post_score": 88,
 *   "Ngày": "2026-05-08",
 *   "ngay": "2026-05-08",
 *   "Đăng vào": "2026-05-08 14:22 UTC",
 *   "dangvao": "2026-05-08 14:22 UTC",
 *   "posts_count": 9,
 *   "Tổng số bài lấy được mỗi lần cào": 9,
 *   "tongsobailayduocmoilancao": 9,
 *   "session_posts_count": 9,
 *   "total_posts_per_scrape": 9,
 *   "row_number": 2,
 *   "rownumber": 2,
 *   "reaction": "celebrate",
 *   "comment": null,
 *   "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:…/",
 *   "final_url": "https://www.linkedin.com/feed/update/urn:li:activity:…/",
 *   "resolved_playwright_session_id": "storage-state-email…",
 *   "webhook_sent_at": "2026-05-10T12:34:56.789Z"
 * }
 * ```
 */
export type PostReactionWebhookFlatBody = Record<string, unknown> & {
  Email_crawl: string;
  ID_session_crawl: string;
  row_number: number;
  rownumber: number;
  reaction: string;
  post_url: string;
};
