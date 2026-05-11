export type LinkedInTopPostStatus = "active" | "completed" | "failed";

export interface LinkedInTopPost {
  id: string;
  /** Tiêu đề / chủ đề bài viết (hiển thị rõ trên card) */
  title: string;
  excerpt: string;
  authorName: string;
  authorRole: string;
  avatarUrl: string;
  status: LinkedInTopPostStatus;
  /** URL bài viết LinkedIn (UGC / activity) */
  postUrl: string;
  /** Tên nhóm nguồn */
  groupName: string;
  /** URL trang nhóm LinkedIn */
  groupUrl: string;
  likesLabel: string;
  commentsCount: number;
  sharesCount: number;
  /** 0–100 — thanh engagement */
  engagementPct: number;
}
