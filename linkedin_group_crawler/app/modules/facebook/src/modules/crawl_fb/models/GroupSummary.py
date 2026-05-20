from dataclasses import dataclass
from src.modules.crawl_fb.models.post import Post
@dataclass
class GroupSummary:
    """
    Entity dùng để đóng gói dữ liệu báo cáo tổng hợp cho một Group.
    """
    group_name: str                  # Tên của Group
    link_group:str
    total_posts_24h: int             # Số lượng bài viết cào được trong 24h qua
    hot_post: Post                    # bài viết
    Intent:str