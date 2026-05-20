from dataclasses import dataclass, field
from typing import Optional, List
#  cấu trúc dữ liệu 1 bài viết mà mình lấy
@dataclass
class Post:
    url: str                         # link bài viết
    date: str                        # thời gian đăng bài 
    reactions: int                   # tổng lượt like,tim......
    comments: int                    # tổng lượt bình luận
    shares: int                      # tổng lượt chia sẽ
    score: int                       # tổng điểm của bài viết công thức ở hàm xử lý chính
    content: str
    media_url: Optional[str] = None  # có thể để none nếu không có video

    images: List[str] = field(default_factory=list) # danh sách nahr nếu có