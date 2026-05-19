/** Copy / icons cho popup engagement (reaction, comment, …). */

export type EngagementFeedbackKind =
  | "reaction"
  | "clear_reaction"
  | "comment"
  | "delete_comment"
  | "edit_comment"
  | "sync";

export const ENGAGEMENT_SUCCESS_COPY: Record<
  EngagementFeedbackKind,
  { title: string; body: string }
> = {
  reaction: {
    title: "Tương tác thành công",
    body: "Bạn đã tương tác với bài viết. Hệ thống đang đồng bộ LinkedIn và sheet ở chế độ nền.",
  },
  clear_reaction: {
    title: "Gỡ tương tác thành công",
    body: "Bạn đã gỡ tương tác. Hệ thống đang đồng bộ LinkedIn và sheet ở chế độ nền.",
  },
  comment: {
    title: "Bình luận thành công",
    body: "Bạn đã gửi bình luận. Hệ thống đang đồng bộ LinkedIn và sheet ở chế độ nền.",
  },
  delete_comment: {
    title: "Xóa bình luận thành công",
    body: "Bình luận đã được gỡ trên màn hình. Hệ thống đang đồng bộ LinkedIn và sheet ở chế độ nền.",
  },
  edit_comment: {
    title: "Chỉnh sửa bình luận thành công",
    body: "Nội dung đã được cập nhật trên màn hình. Hệ thống đang đồng bộ LinkedIn và sheet ở chế độ nền.",
  },
  sync: {
    title: "Làm mới tiến độ thành công",
    body: "Hệ thống đã đọc trạng thái thực tế từ LinkedIn và cập nhật vào sheet.",
  },
};

export const ENGAGEMENT_ERROR_TITLE: Record<EngagementFeedbackKind, string> = {
  reaction: "Tương tác thất bại (Playwright)",
  clear_reaction: "Gỡ tương tác thất bại (Playwright)",
  comment: "Bình luận thất bại (Playwright)",
  delete_comment: "Xóa bình luận thất bại (Playwright)",
  edit_comment: "Chỉnh sửa bình luận thất bại (Playwright)",
  sync: "Đồng bộ tiến độ thất bại",
};

export const ENGAGEMENT_ROLLBACK_NOTE =
  "Trạng thái hiển thị đã được khôi phục về trước khi thao tác.";

export function engagementSuccessIcon(
  kind: EngagementFeedbackKind,
): "favorite" | "delete" | "edit" | "sync" | "comment" {
  if (kind === "reaction" || kind === "clear_reaction") return "favorite";
  if (kind === "delete_comment") return "delete";
  if (kind === "edit_comment") return "edit";
  if (kind === "sync") return "sync";
  return "comment";
}
