# CrawlDataLinkedin - Project Map

Ngay cap nhat: 2026-05-15 (cap nhat KPI leader, sync-progress, slug tu sheet)

Tai lieu nay tom tat chuc nang cua tung khu vuc (backend + frontend), cac file chinh, luong tuong tac, va danh sach API. Noi dung duoc tong hop tu cac file trong repo (link chi tiet o tung muc).

---

## 1) Tong quan kien truc

- Backend FastAPI: [linkedin_group_crawler/app/main.py](linkedin_group_crawler/app/main.py) + routes: [linkedin_group_crawler/app/modules/linkedin/router.py](linkedin_group_crawler/app/modules/linkedin/router.py)
- Frontend Next.js (App Router): [linkedin-crawler-ui/app](linkedin-crawler-ui/app)
- Dong du lieu chinh:
  - Frontend -> Backend (API) -> Playwright / n8n / Google Sheets
  - Backend xu ly, dua ket qua ve frontend va/hoac ghi sheet qua n8n webhook.

Cac tai lieu van hanh quan trong:

- [linkedin_group_crawler/README.md](linkedin_group_crawler/README.md)
- [COMMENTS_DATA_FLOW.md](COMMENTS_DATA_FLOW.md)
- [DATA_STRUCTURE_COMPARISON.md](DATA_STRUCTURE_COMPARISON.md)
- [FIX_COMMENTS_EMPTY_STRING.md](FIX_COMMENTS_EMPTY_STRING.md)
- [OPTIMIZE_COMMENT_DELETE.md](OPTIMIZE_COMMENT_DELETE.md)

---

## 2) Backend (FastAPI) - cau truc va chuc nang

### 2.0 Cau truc thu muc modular moi
Hệ thống được chuyển đổi sang cấu trúc Modular để sẵn sàng mở rộng sang nhiều nền tảng (Facebook, Zalo, v.v.):
- **`app/core/`**: Chứa cấu hình dùng chung (`config.py`), logger, và quản lý browser pool (`playwright_browser_pool.py`).
- **`app/shared/`**: Các service chia sẻ giữa các module (`google_sheet_service.py`, `n8n_webhook_service.py`).
- **`app/modules/linkedin/`**: Đóng gói toàn bộ logic riêng của LinkedIn:
  - `router.py`: Chứa các endpoint API có tiền tố `/api/linkedin/...` và `/api/linkedin/app/...` để tránh xung đột với module khác.
  - `services/`: (Mục tiêu tiếp theo) Di chuyển toàn bộ services liên quan đến LinkedIn vào đây.


### 2.1 Entry point

- [linkedin_group_crawler/app/main.py](linkedin_group_crawler/app/main.py)
  - Tao FastAPI app
  - Add CORS middleware
  - Include router: `router` + `linkedin_app_router`
  - Dam bao thu muc data/state/session ton tai

### 2.2 API routes (router.py)

File: [linkedin_group_crawler/app/modules/linkedin/router.py](linkedin_group_crawler/app/modules/linkedin/router.py)

**Health / status**

- `GET /health` -> `health_check` (kiem tra server)
- `GET /status` -> `system_status` (tra ve config runtime, webhook/gsheet status)

**Login / session**

- `POST /login` -> `login` (login LinkedIn, co the tra `need_otp`)
- `POST /verify` -> `verify_login` (xac minh OTP)

**Profile slug / sheet**

- `POST /linkedin/me/profile-slug` -> `linkedin_me_profile_slug` (lay slug tu Playwright)
- `POST /linkedin/me/profile-slug-sheet-check` -> `linkedin_me_profile_slug_sheet_check` (goi webhook lay sheet, check email)
- `POST /linkedin/me/ensure-profile-slug` -> `linkedin_me_ensure_profile_slug` (neu chua co thi lay slug + post webhook add)

**LinkedIn action (Playwright + webhook)**

- `POST /linkedin/post/react` -> `linkedin_post_react` (reaction / go reaction + ghi sheet)
- `POST /linkedin/post/comment` -> `linkedin_post_comment` (comment + ghi sheet)
- `POST /linkedin/post/comment/delete` -> `linkedin_post_comment_delete` (xoa comment + ghi sheet)
- `POST /linkedin/post/comment/edit` -> `linkedin_post_comment_edit` (sua comment + ghi sheet)
- `POST /linkedin/post/sync-progress` -> `linkedin_post_sync_progress` (doc lai reaction/comment/metrics tren 1 bai + ghi sheet qua webhook)
- `POST /linkedin/sync-all-progress` -> `linkedin_sync_all_progress` (dong bo tat ca bai cua user tu danh sach n8n)

**Crawl**

- `POST /crawl-linkedin-group` -> `crawl_linkedin_group` (crawl mot group, loc theo ngay hoac fallback)

**Webhook n8n (goi tu backend)**

- `POST /n8n/webhook-credentials` -> `forward_credentials_to_n8n` (gui email/pass/max_post)
- `POST /start` -> `start_n8n_workflow` (payload khoi dong workflow n8n)
- `POST /n8n/get-sheet-link` -> `get_sheet_link_via_n8n` (lay link sheet)
- `POST /n8n/webhook-get-post-crawled` -> forward to env webhook
- `POST /n8n/webhook-get-url-group-crawled` -> forward to env webhook
- `POST /n8n/webhook-get-result-crawl-by-id` -> forward to env webhook

**N8n group management**

- `POST /groups/n8n-get-all` -> `n8n_groups_get_all` (doc toan bo nhom theo email)
- `POST /groups/add` -> `n8n_groups_add`
- `POST /groups/remove` -> `n8n_groups_remove`
- `POST /groups/update` -> `n8n_groups_update`
- `POST /groups/add-list-group` -> `add_list_group` (bulk crawl + optionally webhook)

**Filter / Get all posts**

- `POST /filter-data` -> `filter_data` (goi n8n, loc theo ngay)
- `POST /get-all-posts` -> `get_all_posts` (goi n8n, gom theo phien)
- `POST /filter-data` dung chung webhook `N8N_WEBHOOK_GET_ALL_POSTS` (loc ngay tren backend)

**Auth / role / KPI / team (leader)**

- `POST /auth/check-permission` -> `check_permission` (leader/member qua n8n, env `N8N_CHECK_PERMISSION`)
- `POST /auth/verify-leader-code` -> `verify_leader_code` (so sanh `LEADER_CODE` trong .env)
- `POST /kpi/assign` -> `linkedin_assign_kpi` (leader gan KPI, env `N8N_WEBHOOK_ASSIGN_KPI`)
- `POST /kpi/get-all` -> `get_all_kpi` (danh sach member + KPI theo `email_leader`, env `N8N_WEBHOOK_GET_ALL_KPI`)
- `POST /kpi/get-by-email` -> `get_kpi_by_email` (profile_slug + KPI theo email member, env `N8N_WEBHOOK_GET_KPI_BY_EMAIL`)
- `POST /team/add-member` -> `add_member` (env `N8N_WEBHOOK_ADD_MEMBER` — **nen URL rieng**, khong trung check-permission)

**Profiles (sheet)**

- `POST /linkedin/all-profiles` -> `get_all_profiles`
- `POST /linkedin/me/profile-slug-update` -> `update_profile_slug_endpoint` (cap nhat role/slug tren sheet)

**LinkedIn App router (Google Sheet)**

- `GET /linkedin-app/get-all-posts`
- `POST /linkedin-app/get-all-posts`
- `POST /linkedin-app/filter-post`
- `GET /linkedin-app/get-all-groups`
- `POST /linkedin-app/crawl-linkedin-app`

### 2.3 Schemas

- Request models: [linkedin_group_crawler/app/schemas/request_models.py](linkedin_group_crawler/app/schemas/request_models.py)
- Response models: [linkedin_group_crawler/app/schemas/response_models.py](linkedin_group_crawler/app/schemas/response_models.py)

### 2.4 Services (backend)

Thu muc: [linkedin_group_crawler/app/services](linkedin_group_crawler/app/services)

- `auth_service.py`: login, luu session, OTP verify, resolve session state
- `crawler_service.py`: Playwright crawl group feed + parse posts
- `parser_service.py`: parse locator / selector helpers
- `post_reaction_service.py`: reaction + clear reaction
- `post_comment_service.py`: dang comment
- `post_comment_delete_service.py`: xoa comment
- `post_comment_edit_service.py`: sua comment
- `post_comment_sync_service.py`: merge/patch comments, dong bo sheet
- `post_reaction_sync_service.py`: merge/patch reaction, dong bo sheet
- `profile_slug_service.py`: lay slug profile
- `profile_slug_sheet_service.py`: doc/ghi slug via webhook
- `profile_comments_service.py`: doc recent activity / comments
- `group_bulk_import_service.py`: crawl danh sach group
- `n8n_post_filter_service.py`: normalize / filter posts tu n8n
- `n8n_webhook_service.py`: call webhook (post_json, push_start, push_credentials, ...)
- `sync_progress_service.py`: Playwright `goto(post_url)` — doc reaction, comment (marker You/Bạn), metrics; **khong can vao /in/me** khi sync 1 bai
- `google_sheet_service.py`: doc/ghi Google Sheets
- `ranking_service.py`: chon top post / loc bai

### 2.5 Utils

Thu muc: [linkedin_group_crawler/app/utils](linkedin_group_crawler/app/utils)

- `logger.py`: setup logging
- `file_utils.py`: tao folder, luu file
- `datetime_utils.py`: xu ly thoi gian
- `webhook_payload_keys.py` / `webhook_payload_sanitize.py`: normalize payload
- `post_reaction_webhook_ack.py`: danh gia ack webhook

---

## 3) Frontend (Next.js) - cau truc va chuc nang

### 3.1 App Router / Pages

- Root layout: [linkedin-crawler-ui/app/layout.tsx](linkedin-crawler-ui/app/layout.tsx)
- Dashboard home: [linkedin-crawler-ui/app/(dashboard)/page.tsx](linkedin-crawler-ui/app/(dashboard)/page.tsx)
  - Render: `DashboardHomeContent` → LinkedIn: `LinkedInDashboardHomeContent` (member) hoac redirect leader → `/admin/team`
- Leader team admin: [linkedin-crawler-ui/app/(dashboard)/admin/team/page.tsx](linkedin-crawler-ui/app/(dashboard)/admin/team/page.tsx)
  - Chi leader; member → [linkedin-crawler-ui/app/403/page.tsx](linkedin-crawler-ui/app/403/page.tsx)
- Group management: [linkedin-crawler-ui/app/(dashboard)/quan-ly-nhom/page.tsx](linkedin-crawler-ui/app/(dashboard)/quan-ly-nhom/page.tsx)
  - Render: `PlatformGroupManagementContent` (member; leader redirect admin)
- Top posts: [linkedin-crawler-ui/app/top-post/page.tsx](linkedin-crawler-ui/app/top-post/page.tsx)
  - Render: `LinkedInTopPostsPage`

### 3.2 Dashboard core flow

- Dashboard entry: [linkedin-crawler-ui/components/features/dashboard/DashboardHomeContent.tsx](linkedin-crawler-ui/components/features/dashboard/DashboardHomeContent.tsx)
  - Switch Facebook/LinkedIn theo `AppPlatformProvider`
- LinkedIn dashboard: [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedInDashboardHomeContent.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedInDashboardHomeContent.tsx)
  - Member: form + `LinkedInStats` (KPI tuan, actuals tu get-all-posts)
  - Leader: `router.replace("/admin/team")` khi vao home
  - Form crawler: [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlerConfigCard.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlerConfigCard.tsx)
  - Ket qua: [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlResultsSection.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlResultsSection.tsx)
  - Bang phien + modal: [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlSessionsTableCore.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlSessionsTableCore.tsx)
  - Modal phien: [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostsModal.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostsModal.tsx)
  - Modal chi tiet post: [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostDetailModal.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostDetailModal.tsx)

### 3.3 Leader — quan ly doi & KPI

- Page: [linkedin-crawler-ui/app/(dashboard)/admin/team/page.tsx](linkedin-crawler-ui/app/(dashboard)/admin/team/page.tsx)
- Noi dung: [linkedin-crawler-ui/components/features/linkedin/admin/team/AdminTeamPageContent.tsx](linkedin-crawler-ui/components/features/linkedin/admin/team/AdminTeamPageContent.tsx)
  - `fetchTeamMembers` → `POST /kpi/get-all` (`email_leader`)
  - Sau do `get-all-posts` **lan luot theo email tung member** (gop `teamMembersPostsResult`) — **khong** dung email leader de dem KPI
  - Dem thuc te: [linkedin-crawler-ui/lib/admin-team-kpi-metrics.ts](linkedin-crawler-ui/lib/admin-team-kpi-metrics.ts) (`email_crawl` = email member)
  - Bang + modal KPI: `AdminTeamTable`, `AssignKpiModal` (xem KPI theo tuan, so sanh actual vs target)
  - `AddMemberModal` → `POST /team/add-member`

### 3.4 Auth UI

- [linkedin-crawler-ui/components/features/auth/WelcomeRoleModal.tsx](linkedin-crawler-ui/components/features/auth/WelcomeRoleModal.tsx): chon leader/member lan dau
- [linkedin-crawler-ui/components/features/auth/ForbiddenPage.tsx](linkedin-crawler-ui/components/features/auth/ForbiddenPage.tsx): 403
- [linkedin-crawler-ui/components/features/dashboard/DashboardSidebar.tsx](linkedin-crawler-ui/components/features/dashboard/DashboardSidebar.tsx): login, OTP, nav leader → `/admin/team`

### 3.5 Group management

- Group management page content: [linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInGroupManagementPageContent.tsx](linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInGroupManagementPageContent.tsx)
- N8n managed groups: [linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInN8nManagedGroupsSection.tsx](linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInN8nManagedGroupsSection.tsx)
- Local group list: [linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInGroupsToCrawlSection.tsx](linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInGroupsToCrawlSection.tsx)

### 3.6 Top-post page (UI demo / mock)

- Main page: [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsPage.tsx](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsPage.tsx)
- Card/UI helpers: [linkedin-crawler-ui/components/features/linkedin/top-post](linkedin-crawler-ui/components/features/linkedin/top-post)
  - Mock data, stats row, sidebar, pagination

### 3.7 Hooks / Services / Lib

- Hook: [linkedin-crawler-ui/hooks/useDashboardCrawler.ts](linkedin-crawler-ui/hooks/useDashboardCrawler.ts)
  - Form, crawl sessions, filter, role, `teamMembers`, `memberKpi`, `memberKpiStats`
  - Leader: `teamMembersPostsResult` + `loadLeaderTeamPostsForMemberEmails` (get-all-posts tung member)
  - `fetchTeamMembers`, `handleSyncAllProgress`, `checkPermission` qua sidebar
- API client: [linkedin-crawler-ui/services/linkedinCrawlerService.ts](linkedin-crawler-ui/services/linkedinCrawlerService.ts)
  - Them: `syncPostProgress`, `syncAllProgress`, `getAllKpi`, `getKpiByEmail`, `assignKpi`, `checkPermission`, `addMember`, `verifyLeaderCode`, `updateProfileSlug`
- Types: [linkedin-crawler-ui/types/api.ts](linkedin-crawler-ui/types/api.ts)
  - `KpiMemberData`, `CrawlSessionGroup`, sync/KPI request models
- Lib helpers: [linkedin-crawler-ui/lib](linkedin-crawler-ui/lib)
  - `env.ts`, `credentials.ts`, `date-helpers.ts`
  - `kpi-month-weeks.ts`: tuan lich T2–CN, merge KPI payload
  - `admin-team-kpi-metrics.ts`: dem phiên/bài/comment/tuong tac theo `email_crawl` + khoang ngay
  - `merge-crawl-session-groups.ts`: gop nhieu lan get-all-posts (leader)
  - `LinkedIn-resolve-profile-slug-from-sheet.ts`: slug tu sheet / `kpi/get-by-email` (sync 1 bai, **khong** Playwright /in/me)
  - `LinkedIn-appComments.ts`, `LinkedIn-postReactionWebhookBody.ts`, `LinkedIn-n8n-groups-normalize.ts`, ...

---

## 4) Tuong tac giua cac file (backend <-> frontend)

### 4.1 Form crawl va ket qua (frontend)

- UI form: [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlerConfigCard.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlerConfigCard.tsx)
  - Goi `getAllN8nGroups` -> [linkedin-crawler-ui/services/linkedinCrawlerService.ts](linkedin-crawler-ui/services/linkedinCrawlerService.ts)
  - Backend: `POST /groups/n8n-get-all`

- Start workflow: `startN8nWorkflow` -> backend `POST /start` -> n8n webhook

- Ket qua: [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlResultsSection.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlResultsSection.tsx)
  - `handleGetAllPosts` -> backend `POST /get-all-posts`
  - `handleFilter*` -> backend `POST /filter-data`

### 4.2 Session post detail / actions

- Modal post: [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostDetailModal.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostDetailModal.tsx)
  - Reaction -> `POST /linkedin/post/react`
  - Comment -> `POST /linkedin/post/comment`
  - Delete comment -> `POST /linkedin/post/comment/delete` (van can `getMyProfileSlug` → recent-activity)
  - Edit comment -> `POST /linkedin/post/comment/edit` (van can slug Playwright)
  - **Sau popup OK** (comment/reaction/...): `runSyncProgress` → `resolveProfileSlugFromSheetForEmail` → `POST /linkedin/post/sync-progress`
  - Sync: Playwright **chi** `goto(post_url)`; slug chi de thoa API, doc comment bang marker **You/Bạn**

Backend ghi sheet qua webhook `N8N_WEBHOOK_REACTION` (alias `N8N_WEBHOOK_POST_REACTION`).

### 4.4 Leader — KPI va feed posts

```text
POST /kpi/get-all (email_leader)
  → danh sach member + profile_slug + kpi[]
  → voi moi email member: POST /get-all-posts { email: member }
  → mergeCrawlSessionGroups → teamMembersPostsResult
  → computeMemberActualsInYmdRange(email_member, ...) cho bang + stats
```

Modal **Xem KPI**: chon tuan → `findKpiOverlappingWindow` + actuals cung khoang ngay tren feed da gop.

### 4.3 Group management (n8n)

- UI: [linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInN8nManagedGroupsSection.tsx](linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInN8nManagedGroupsSection.tsx)
  - `getAllN8nGroups` -> `POST /groups/n8n-get-all`
  - `addN8nGroup` -> `POST /groups/add`
  - `updateN8nGroup` -> `POST /groups/update`
  - `removeN8nGroup` -> `POST /groups/remove`
  - `addListGroupBulk` -> `POST /groups/add-list-group`

---

## 5) Luu tru du lieu

- Backend data output: [linkedin_group_crawler/data](linkedin_group_crawler/data)
  - `raw/`, `output/`
- Storage / session: [linkedin_group_crawler/storage](linkedin_group_crawler/storage)
  - `session/`, `sessions/`, `runtime/`, `linkedin_state.json`

---

## 6) Ghi chu ve config

Backend: [linkedin_group_crawler/.env](linkedin_group_crawler/.env) — mau: [linkedin_group_crawler/.env.example](linkedin_group_crawler/.env.example)

| Bien .env | Endpoint / muc dich |
|-----------|---------------------|
| `N8N_WEBHOOK_URL` | `/n8n/webhook-credentials` (email/pass) — **khong** dung key `N8N_WEBHOOK` |
| `N8N_WEBHOOK_START` | `POST /start` |
| `N8N_WEBHOOK_GET_ALL_POSTS` | `POST /get-all-posts`, `POST /filter-data` |
| `N8N_WEBHOOK_REACTION` | reaction, comment webhook, **sync-progress**, sync-all |
| `N8N_WEBHOOK_COMMENT` | (tu chon) webhook rieng sau comment |
| `N8N_WEBHOOK_GET_PROFILE_SLUGS` / `N8N_WEBHOOK_ADD_PROFILE_SLUG` | profile slug sheet |
| `N8N_CHECK_PERMISSION` | `POST /auth/check-permission` |
| `N8N_WEBHOOK_ASSIGN_KPI` | `POST /kpi/assign` |
| `N8N_WEBHOOK_GET_ALL_KPI` | `POST /kpi/get-all` |
| `N8N_WEBHOOK_GET_KPI_BY_EMAIL` | `POST /kpi/get-by-email` (slug + KPI member) |
| `N8N_WEBHOOK_ADD_MEMBER` | `POST /team/add-member` — **URL rieng**, khong trung check-permission |
| `LEADER_CODE` | `POST /auth/verify-leader-code` |
| `API_KEY` | header `x-api-key` |

Frontend: [linkedin-crawler-ui/.env.local](linkedin-crawler-ui/.env.local)

- `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL`
- `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_KEY`

---

## 7) Checklist file chinh theo chuc nang

**Login / session**

- [linkedin_group_crawler/app/modules/linkedin/services/auth_service.py](linkedin_group_crawler/app/modules/linkedin/services/auth_service.py)
- [linkedin_group_crawler/app/modules/linkedin/router.py](linkedin_group_crawler/app/modules/linkedin/router.py)
- [linkedin-crawler-ui/services/linkedinCrawlerService.ts](linkedin-crawler-ui/services/linkedinCrawlerService.ts)

**Crawl + top post**

- [linkedin_group_crawler/app/modules/linkedin/services/crawler_service.py](linkedin_group_crawler/app/modules/linkedin/services/crawler_service.py)
- [linkedin_group_crawler/app/modules/linkedin/services/ranking_service.py](linkedin_group_crawler/app/modules/linkedin/services/ranking_service.py)
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlResultsSection.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlResultsSection.tsx)

**N8n group management**

- [linkedin_group_crawler/app/shared/services/n8n_webhook_service.py](linkedin_group_crawler/app/shared/services/n8n_webhook_service.py)
- [linkedin_group_crawler/app/modules/linkedin/router.py](linkedin_group_crawler/app/modules/linkedin/router.py)
- [linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInN8nManagedGroupsSection.tsx](linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInN8nManagedGroupsSection.tsx)

**Comment / reaction**

- [linkedin_group_crawler/app/modules/linkedin/services/post_comment_service.py](linkedin_group_crawler/app/modules/linkedin/services/post_comment_service.py)
- [linkedin_group_crawler/app/modules/linkedin/services/post_comment_delete_service.py](linkedin_group_crawler/app/modules/linkedin/services/post_comment_delete_service.py)
- [linkedin_group_crawler/app/modules/linkedin/services/post_comment_edit_service.py](linkedin_group_crawler/app/modules/linkedin/services/post_comment_edit_service.py)
- [linkedin_group_crawler/app/modules/linkedin/services/post_reaction_service.py](linkedin_group_crawler/app/modules/linkedin/services/post_reaction_service.py)
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostDetailModal.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostDetailModal.tsx)

---

Neu ban muon, toi co the bo sung mo ta chi tiet hon cho tung file con trong [linkedin_group_crawler/app/modules/linkedin/services](linkedin_group_crawler/app/modules/linkedin/services) va [linkedin-crawler-ui/components](linkedin-crawler-ui/components), hoac xuat ra so do Mermaid (backend <-> frontend <-> n8n) de de doc hon.

---

## 8) Chi tiet tung file trong backend services

- **LinkedIn specific services (Thu muc: [linkedin_group_crawler/app/modules/linkedin/services](linkedin_group_crawler/app/modules/linkedin/services))**
  - [linkedin_group_crawler/app/modules/linkedin/services/auth_service.py](linkedin_group_crawler/app/modules/linkedin/services/auth_service.py): Login LinkedIn, luu storage state, xu ly OTP, resolve session id theo email, tim selector login, ghi artifacts (screenshot/html) khi loi.
  - [linkedin_group_crawler/app/modules/linkedin/services/crawler_service.py](linkedin_group_crawler/app/modules/linkedin/services/crawler_service.py): Mo group URL, scroll, parse post, lay group_name, luu raw html; goi parse_post_locator tu parser_service.
  - [linkedin_group_crawler/app/modules/linkedin/services/group_bulk_import_service.py](linkedin_group_crawler/app/modules/linkedin/services/group_bulk_import_service.py): Crawl hang loat URL nhom, parse member count, ten nhom, tra ve danh sach ket qua.
  - [linkedin_group_crawler/app/modules/linkedin/services/n8n_post_filter_service.py](linkedin_group_crawler/app/modules/linkedin/services/n8n_post_filter_service.py): Normalize payload n8n, parse ngay bai viet, loc theo date range, gom session, map cac key alias.
  - [linkedin_group_crawler/app/modules/linkedin/services/parser_service.py](linkedin_group_crawler/app/modules/linkedin/services/parser_service.py): Parse post element LinkedIn (author, content, posted_at_raw, reactions, comments, reposts, post_url) voi selector fallback.
  - [linkedin_group_crawler/app/modules/linkedin/services/post_comment_service.py](linkedin_group_crawler/app/modules/linkedin/services/post_comment_service.py): Playwright mo post detail, tim editor comment, go comment, submit va verify.
  - [linkedin_group_crawler/app/modules/linkedin/services/post_comment_delete_service.py](linkedin_group_crawler/app/modules/linkedin/services/post_comment_delete_service.py): Xoa comment tu post detail / recent-activity, match text, mo menu more, click Delete va confirm.
  - [linkedin_group_crawler/app/modules/linkedin/services/post_comment_edit_service.py](linkedin_group_crawler/app/modules/linkedin/services/post_comment_edit_service.py): Sua comment tu post detail (menu Edit -> contenteditable -> Save changes) va verify.
  - [linkedin_group_crawler/app/modules/linkedin/services/post_comment_sync_service.py](linkedin_group_crawler/app/modules/linkedin/services/post_comment_sync_service.py): Merge comment vao sheet row, patch comments cell, dong bo danh sach qua webhook ghi de.
  - [linkedin_group_crawler/app/modules/linkedin/services/post_reaction_service.py](linkedin_group_crawler/app/modules/linkedin/services/post_reaction_service.py): Playwright reaction (like/love/celebrate/support/insightful/funny) hoac clear reaction tren post.
  - [linkedin_group_crawler/app/modules/linkedin/services/post_reaction_sync_service.py](linkedin_group_crawler/app/modules/linkedin/services/post_reaction_sync_service.py): Dong bo reaction vao sheet; fetch posts tu n8n, match url+email, build webhook payload, skip Playwright neu sheet da co.
  - [linkedin_group_crawler/app/modules/linkedin/services/profile_comments_service.py](linkedin_group_crawler/app/modules/linkedin/services/profile_comments_service.py): Crawl recent-activity comments theo public_id, parse activity_url, group_post/activity id, comment text va time.
  - [linkedin_group_crawler/app/modules/linkedin/services/profile_slug_service.py](linkedin_group_crawler/app/modules/linkedin/services/profile_slug_service.py): Lay profile slug tu /in/me hoac menu Me, validate slug, tra ve profile_url.
  - [linkedin_group_crawler/app/modules/linkedin/services/profile_slug_sheet_service.py](linkedin_group_crawler/app/modules/linkedin/services/profile_slug_sheet_service.py): Doc webhook danh sach profile slug, normalize rows, tim email khop, (tu chon) ghi slug moi qua webhook.
  - [linkedin_group_crawler/app/modules/linkedin/services/ranking_service.py](linkedin_group_crawler/app/modules/linkedin/services/ranking_service.py): Tinh score tu likes/comments/reposts, loc theo ngay muc tieu, chon top post, pick bai moi nhat fallback.
  - [linkedin_group_crawler/app/modules/linkedin/services/sync_progress_service.py](linkedin_group_crawler/app/modules/linkedin/services/sync_progress_service.py): `sync_post_engagement` / `sync_post_engagement_on_page` — doc reaction, comment (You/Bạn), metrics; goto truc tiep `post_url`.

- **Shared / General services (Thu muc: [linkedin_group_crawler/app/shared/services](linkedin_group_crawler/app/shared/services))**
  - [linkedin_group_crawler/app/shared/services/google_sheet_service.py](linkedin_group_crawler/app/shared/services/google_sheet_service.py): Ket noi Google Sheets bang service account; doc/ghi du lieu, map header alias.
  - [linkedin_group_crawler/app/shared/services/n8n_webhook_service.py](linkedin_group_crawler/app/shared/services/n8n_webhook_service.py): Goi webhook n8n (credentials, start, get sheet link, post_json); xu ly timeout va preview response.


---

## 9) Chi tiet tung file trong frontend components

Luu y: Trong code co 2 bo component tuong tu nhau:

- [linkedin-crawler-ui/components/features/dashboard](linkedin-crawler-ui/components/features/dashboard) (bo chung / wrapper)
- [linkedin-crawler-ui/components/features/linkedin/dashboard](linkedin-crawler-ui/components/features/linkedin/dashboard) (bo LinkedIn cu the, them reaction/comment/delete/edit)

### 9.1 components/features/dashboard

- [linkedin-crawler-ui/components/features/dashboard/BentoStatsRow.tsx](linkedin-crawler-ui/components/features/dashboard/BentoStatsRow.tsx): Hien thi 3 the thong ke (members, velocity, accuracy) tu `useDashboard`.
- [linkedin-crawler-ui/components/features/dashboard/constants.ts](linkedin-crawler-ui/components/features/dashboard/constants.ts): Hang so cho dashboard (page size, avatar URL).
- [linkedin-crawler-ui/components/features/dashboard/CrawlerConfigCard.tsx](linkedin-crawler-ui/components/features/dashboard/CrawlerConfigCard.tsx): Form crawler (email/pass/mode/date/urls) + picker nhom tu n8n.
- [linkedin-crawler-ui/components/features/dashboard/CrawlResultsSection.tsx](linkedin-crawler-ui/components/features/dashboard/CrawlResultsSection.tsx): Khu vuc loc + bang phien; goi `handleGetAllPosts`, `handleFilter*`.
- [linkedin-crawler-ui/components/features/dashboard/CrawlSessionsTableCore.tsx](linkedin-crawler-ui/components/features/dashboard/CrawlSessionsTableCore.tsx): Bang phien + pagination; mo `SessionPostsModal`.
- [linkedin-crawler-ui/components/features/dashboard/dashboard-context.tsx](linkedin-crawler-ui/components/features/dashboard/dashboard-context.tsx): Context provider cho `useDashboard` (DashboardCrawlerValue).
- [linkedin-crawler-ui/components/features/dashboard/dashboard-helpers.ts](linkedin-crawler-ui/components/features/dashboard/dashboard-helpers.ts): Helper status badge + derive group name.
- [linkedin-crawler-ui/components/features/dashboard/DashboardAuthGate.tsx](linkedin-crawler-ui/components/features/dashboard/DashboardAuthGate.tsx): Gate yeu cau email/pass; doc/ghi credentials tu localStorage.
- [linkedin-crawler-ui/components/features/dashboard/DashboardHeader.tsx](linkedin-crawler-ui/components/features/dashboard/DashboardHeader.tsx): Header top (nav, search, icon, avatar).
- [linkedin-crawler-ui/components/features/dashboard/DashboardHomeContent.tsx](linkedin-crawler-ui/components/features/dashboard/DashboardHomeContent.tsx): Chon noi dung LinkedIn / Facebook theo platform.
- [linkedin-crawler-ui/components/features/dashboard/DashboardPlatformSwitcher.tsx](linkedin-crawler-ui/components/features/dashboard/DashboardPlatformSwitcher.tsx): Switch platform (linkedin/facebook) luu localStorage.
- [linkedin-crawler-ui/components/features/dashboard/DashboardShell.tsx](linkedin-crawler-ui/components/features/dashboard/DashboardShell.tsx): Wrap AppPlatform + DashboardProvider + Sidebar + AuthGate.
- [linkedin-crawler-ui/components/features/dashboard/DashboardSidebar.tsx](linkedin-crawler-ui/components/features/dashboard/DashboardSidebar.tsx): Sidebar + login LinkedIn (OTP flow) + nav.
- [linkedin-crawler-ui/components/features/dashboard/index.ts](linkedin-crawler-ui/components/features/dashboard/index.ts): Export tong hop cho dashboard.
- [linkedin-crawler-ui/components/features/dashboard/linkedin-reaction-icons.tsx](linkedin-crawler-ui/components/features/dashboard/linkedin-reaction-icons.tsx): Icon + label reaction; parse alias reaction tu sheet.
- [linkedin-crawler-ui/components/features/dashboard/n8n-sheet-helpers.ts](linkedin-crawler-ui/components/features/dashboard/n8n-sheet-helpers.ts): Helper doc row, post_url, row_number, merge metadata vao `sheet_row`.
- [linkedin-crawler-ui/components/features/dashboard/PlatformGroupManagementContent.tsx](linkedin-crawler-ui/components/features/dashboard/PlatformGroupManagementContent.tsx): Switch group management LinkedIn/Facebook.
- [linkedin-crawler-ui/components/features/dashboard/post-sheet-engagement.ts](linkedin-crawler-ui/components/features/dashboard/post-sheet-engagement.ts): Parse reaction/comment automation tu sheet, build patch reaction.
- [linkedin-crawler-ui/components/features/dashboard/SessionPostDetailModal.tsx](linkedin-crawler-ui/components/features/dashboard/SessionPostDetailModal.tsx): Modal chi tiet bai + reaction/comment (ban chung).
- [linkedin-crawler-ui/components/features/dashboard/SessionPostsModal.tsx](linkedin-crawler-ui/components/features/dashboard/SessionPostsModal.tsx): Modal danh sach bai trong mot phien.
- [linkedin-crawler-ui/components/features/dashboard/SheetCommentStatus.tsx](linkedin-crawler-ui/components/features/dashboard/SheetCommentStatus.tsx): Hien thi trang thai comment automation (chip/table).
- [linkedin-crawler-ui/components/features/dashboard/SheetInteractionStatus.tsx](linkedin-crawler-ui/components/features/dashboard/SheetInteractionStatus.tsx): Hien thi trang thai reaction (chip/table).
- [linkedin-crawler-ui/components/features/dashboard/types.ts](linkedin-crawler-ui/components/features/dashboard/types.ts): Type cho bang phien va status.

### 9.2 components/features/linkedin/dashboard

- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedInDashboardHomeContent.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedInDashboardHomeContent.tsx): Layout chinh LinkedIn (title + form + results).
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlerConfigCard.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlerConfigCard.tsx): Form crawler LinkedIn (giong dashboard, them class/style rieng).
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlResultsSection.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlResultsSection.tsx): Khu vuc loc + bang phien cho LinkedIn.
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlSessionsTableCore.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-CrawlSessionsTableCore.tsx): Bang phien LinkedIn, mo `LinkedIn-SessionPostsModal`.
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostsModal.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostsModal.tsx): Modal danh sach bai cua phien, mo modal chi tiet.
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostDetailModal.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SessionPostDetailModal.tsx): Modal chi tiet post (reaction/comment/delete/edit + popup OK → sync-progress; slug tu sheet cho sync).
- [linkedin-crawler-ui/components/features/linkedin/stats/LinkedInStats.tsx](linkedin-crawler-ui/components/features/linkedin/stats/LinkedInStats.tsx): KPI member (tuan hien tai, actuals tu get-all-posts).
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-n8n-sheet-helpers.ts](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-n8n-sheet-helpers.ts): Helper read row number, post_url, session meta cho sheet_row.
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-post-sheet-engagement.ts](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-post-sheet-engagement.ts): Parse reaction/comment automation tu sheet; build patch.
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-reaction-icons.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-reaction-icons.tsx): Icon + label reaction + alias mapping.
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SheetCommentStatus.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SheetCommentStatus.tsx): Chip/table status comment.
- [linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SheetInteractionStatus.tsx](linkedin-crawler-ui/components/features/linkedin/dashboard/LinkedIn-SheetInteractionStatus.tsx): Chip/table status reaction.
- [linkedin-crawler-ui/components/features/linkedin/dashboard/index.ts](linkedin-crawler-ui/components/features/linkedin/dashboard/index.ts): Export tong hop LinkedIn dashboard.

### 9.3 components/features/linkedin/group-management

- [linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInGroupManagementPageContent.tsx](linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInGroupManagementPageContent.tsx): Trang quan ly nhom (wrapper).
- [linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInN8nManagedGroupsSection.tsx](linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInN8nManagedGroupsSection.tsx): CRUD nhom qua n8n (get/add/update/remove/bulk).
- [linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInGroupsToCrawlSection.tsx](linkedin-crawler-ui/components/features/linkedin/group-management/LinkedInGroupsToCrawlSection.tsx): Danh sach URL nhom local tu form; chon/export CSV/JSON.
- [linkedin-crawler-ui/components/features/linkedin/group-management/index.ts](linkedin-crawler-ui/components/features/linkedin/group-management/index.ts): Export group management components.

### 9.4 components/features/linkedin/top-post

- [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsPage.tsx](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsPage.tsx): Page top posts (mock data + pagination).
- [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostCard.tsx](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostCard.tsx): Card hien thi bai top (author, group, stats).
- [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsAppBar.tsx](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsAppBar.tsx): App bar top-post (search, nav).
- [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsSidebar.tsx](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsSidebar.tsx): Sidebar top-post (nav, help).
- [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsStatsRow.tsx](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsStatsRow.tsx): So lieu tong quan (mock).
- [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsPagination.tsx](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostsPagination.tsx): Pagination control.
- [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostHelpers.ts](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostHelpers.ts): Helpers map status label + class.
- [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostConstants.ts](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostConstants.ts): Hang so avatar header.
- [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostMockData.ts](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostMockData.ts): Du lieu mock top posts.
- [linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostTypes.ts](linkedin-crawler-ui/components/features/linkedin/top-post/LinkedInTopPostTypes.ts): Types cho top post.
- [linkedin-crawler-ui/components/features/linkedin/top-post/index.ts](linkedin-crawler-ui/components/features/linkedin/top-post/index.ts): Export top-post page/types.

### 9.5 components/features/linkedin/admin/team

- [linkedin-crawler-ui/components/features/linkedin/admin/team/AdminTeamPageContent.tsx](linkedin-crawler-ui/components/features/linkedin/admin/team/AdminTeamPageContent.tsx): Stats + loc ngay + bang doi.
- [linkedin-crawler-ui/components/features/linkedin/admin/team/AdminTeamTable.tsx](linkedin-crawler-ui/components/features/linkedin/admin/team/AdminTeamTable.tsx): Bang member, nut Giao/Xem/Sua KPI.
- [linkedin-crawler-ui/components/features/linkedin/admin/team/AssignKpiModal.tsx](linkedin-crawler-ui/components/features/linkedin/admin/team/AssignKpiModal.tsx): Giao/sua/xem KPI theo tuan.
- [linkedin-crawler-ui/components/features/linkedin/admin/team/AdminTeamStats.tsx](linkedin-crawler-ui/components/features/linkedin/admin/team/AdminTeamStats.tsx): The tong hop doi.
- [linkedin-crawler-ui/components/features/linkedin/admin/team/AddMemberModal.tsx](linkedin-crawler-ui/components/features/linkedin/admin/team/AddMemberModal.tsx): Them member.

### 9.6 components/features/facebook

- [linkedin-crawler-ui/components/features/facebook/FacebookDashboardHomeContent.tsx](linkedin-crawler-ui/components/features/facebook/FacebookDashboardHomeContent.tsx): Placeholder khu vuc dashboard Facebook.
- [linkedin-crawler-ui/components/features/facebook/FacebookGroupManagementPlaceholder.tsx](linkedin-crawler-ui/components/features/facebook/FacebookGroupManagementPlaceholder.tsx): Placeholder quan ly nhom Facebook.
- [linkedin-crawler-ui/components/features/facebook/index.ts](linkedin-crawler-ui/components/features/facebook/index.ts): Export placeholder Facebook.

### 9.7 components/providers

- [linkedin-crawler-ui/components/providers/AppPlatformProvider.tsx](linkedin-crawler-ui/components/providers/AppPlatformProvider.tsx): Context chon platform (linkedin/facebook) + luu localStorage.

### 9.8 components/ui

- [linkedin-crawler-ui/components/ui/MaterialIcon.tsx](linkedin-crawler-ui/components/ui/MaterialIcon.tsx): Wrapper Material Symbols (name, filled, className).
- [linkedin-crawler-ui/components/ui/index.ts](linkedin-crawler-ui/components/ui/index.ts): Export UI components.
