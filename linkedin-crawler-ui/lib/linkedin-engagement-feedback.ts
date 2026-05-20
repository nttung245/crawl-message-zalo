/** Copy / icons cho popup làm mới tiến độ. */

export type EngagementFeedbackKind = "sync";

export const ENGAGEMENT_SUCCESS_COPY: Record<
  EngagementFeedbackKind,
  { title: string; body: string }
> = {
  sync: {
    title: "Làm mới tiến độ thành công",
    body: "Hệ thống đã đọc trạng thái thực tế từ LinkedIn và cập nhật vào sheet.",
  },
};

export const ENGAGEMENT_ERROR_TITLE: Record<EngagementFeedbackKind, string> = {
  sync: "Đồng bộ tiến độ thất bại",
};

export const ENGAGEMENT_ROLLBACK_NOTE =
  "Trạng thái hiển thị đã được khôi phục về trước khi thao tác.";

export function engagementSuccessIcon(
  kind: EngagementFeedbackKind,
): "sync" {
  if (kind === "sync") return "sync";
  return "sync";
}
