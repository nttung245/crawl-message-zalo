# zalo-crawl-completion-feedback Specification

## Purpose
Defines the surface that tells the operator "the crawl finished" and
shows the per-job message and image counts. Addresses the user
complaint: "Crawl (Hiện không thấy bất kỳ thông báo messages hay images
sau khi click button crawl)".

## Requirements

### Requirement: ZaloCrawlProgressPanel is mounted in the Crawl tab
The component `components/features/zalo/dashboard/ZaloCrawlProgressPanel.tsx` MUST be rendered inside `components/features/zalo/dashboard/ZaloCrawlerConfigCard.tsx` (after the group list, before the closing `</section>`), receiving `jobs={flow.jobs}` and `summary={flow.summary}` as props.

#### Scenario: Crawl tab shows the progress panel
- **WHEN** the user navigates to the Crawl tab
- **THEN** the five big-number cards "Tổng nhóm / Đang chờ / Hoàn tất / Tin nhắn thu thập / Ảnh tìm thấy" are visible above the fold

#### Scenario: Progress panel updates as jobs finish
- **WHEN** an SSE event updates `job.progress.messages_collected` or `images_found`
- **THEN** the corresponding big-number card re-renders within one animation frame

### Requirement: Toast on crawl job creation
The hook `hooks/useZaloCrawlerFlow.ts::launchRows` MUST call `toast.success("Đã tạo N job crawl", { description: "Theo dõi tiến độ ngay bên dưới." })` immediately after the success count is computed. The call MUST happen exactly once per crawl batch, not per job.

#### Scenario: Operator clicks Crawl on 3 groups
- **WHEN** `launchRows` successfully creates 3 jobs
- **THEN** exactly one success toast appears with "Đã tạo 3 job crawl" and the inline banner shows the same count

### Requirement: Toast per job completion
For each job, when the SSE event stream reports `status="completed"` with `messages_collected > 0` or `images_found > 0`, the hook MUST call `toast.info("Job ${short_id}: ${messages} tin nhắn, ${images} ảnh")`. Toasts older than 3 seconds MUST be auto-dismissed to avoid spam.

#### Scenario: One job finishes
- **WHEN** the SSE event for job `abc-123` reports `status="completed", messages_collected=12, images_found=3`
- **THEN** a toast appears reading "Job abc-123: 12 tin nhắn, 3 ảnh" and is auto-dismissed after 3s

#### Scenario: 20 jobs finish in quick succession
- **WHEN** 20 jobs report completion in the same SSE batch
- **THEN** 20 toasts are queued, each auto-dismissing after 3s, and the progress panel's big-number cards show the cumulative counts

### Requirement: Crawl counts are visible without switching tabs
The user MUST see the "Tin nhắn thu thập" and "Ảnh tìm thấy" totals on the Crawl tab itself. The existing `ZaloCrawlResultSection` (per-group collapsible breakdown) is optional and MAY be mounted below the progress panel.

#### Scenario: Operator stays on Crawl tab
- **WHEN** the operator clicks Crawl and waits for completion
- **THEN** they see "Tin nhắn thu thập: N" and "Ảnh tìm thấy: M" on the same tab, without needing to switch to Library or any other tab
