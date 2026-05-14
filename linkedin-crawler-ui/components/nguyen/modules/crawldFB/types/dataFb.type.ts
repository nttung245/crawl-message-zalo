export interface DataFBResponse{
    group_name: string;
    total_posts_24h: number;
    
    link_group: string;

    url: string;
    date: string;
    dateCrawl:Date,
    intent?: string;
    reactions: number;
    comments: number;
    shares: number;
    score: number;
    content?: string;
    media_url: string | null;
    images: string[];
}
export interface CrawlIntentOption {
    value: string;
    label: string;
}
export interface FacebookGroupDTO {
    group_name: string;             // Tương ứng: str
    url: string;                    // Tương ứng: str
    intent: string;                 // Tương ứng: str
    members?: number | null;        // Tương ứng: Optional[int]
    last_crawl?: string | null;    // Tương ứng: Optional[str] (Lưu ý chữ C viết hoa theo đúng model API)
    date_crawl?: Date | null;    // Tương ứng: Optional[str] (Lưu ý chữ C viết hoa theo đúng model API)
    posts_per_week?: number | null; // Tương ứng: Optional[int]
    health_score?: number | null;   // Tương ứng: Optional[float]
    chay_24h?: boolean | null;      // Tương ứng: Optional[bool]
    status?: "ACTIVE" | "IDLE" | "DEAD"; // Giữ lại cho UI hiển thị (nếu cần)
}