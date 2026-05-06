export type CrawlStatus = "Completed" | "Processing" | "Failed";

/** Nguồn hiển thị bảng phiên trong Kết quả Crawl. */
export type CrawlTableViewMode = "all" | "filtered";

export interface CrawlResultRow {
  id: string;
  groupName: string;
  groupPath: string;
  groupUrl?: string;
  status: CrawlStatus;
  posts: number;
  topAuthor: string | null;
  date: string;
  likes: string | null;
  reposts: string | null;
  postUrl?: string | null;
  errorMessage?: string | null;
  action: "view" | "retry";
}
