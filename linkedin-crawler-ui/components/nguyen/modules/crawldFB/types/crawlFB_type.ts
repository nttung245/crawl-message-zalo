export interface CrawlFBType {
  name: string;
  url: string;
}
export interface AccountCrawlFBType {
  useName?: string;
  password?: string;
}

export interface CrawlFBRequest {
      groups:CrawlFBType[],
      tkFB:AccountCrawlFBType
}

export interface PostType {
    group_name: string;
    total_posts_24h: number;
    url: string;
    date: string;
    reactions: number;
    comments: number;
    shares: number;
    score: number;
    content?: string;
    media_url: string | null; // Optional[str] trong Python sẽ là string hoặc null
    images: string[];         // List[str] trong Python
}

// 2. Type cho tổng hợp nhóm (Đồng bộ với class GroupSummary)
export interface GroupSummaryType {
    group_name: string;
    total_posts_24h: number;
    hot_post?: PostType; // Chứa đối tượng Post ở trên
}

// 3. Type tổng quát cho API Response (Đồng bộ với dict return ở hàm FetchDataDirectly)
export interface FetchCrawlResponse {
    status: "success" | "error";
    message: string;
    data: GroupSummaryType[]; // Mảng các GroupSummary, nếu không có bài nào thì là []
}