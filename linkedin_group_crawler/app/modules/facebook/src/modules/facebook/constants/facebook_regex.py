import re

# ════════════════════════════════════════════════════════════
#  REGEX — URL BÀI VIẾT
# ════════════════════════════════════════════════════════════
# dùng để lấy url thừ fb
# /photo/|/photos /: # Đường dẫn mở Trình xem ảnh của FB (vd: facebook.com/photo/?fbid=12345)
# 1. NHẬN DIỆN BÀI VIẾT THÔNG THƯỜNG (TEXT / LINK SHARE)
# Bao gồm các link chứa /posts/, /permalink/ hoặc dạng classic ?story_fbid=
POST_URL_RE = re.compile(
    r'/(posts|permalink|questions)/'
    r'|[?&]story_fbid=', 
    re.IGNORECASE
)



# 3. NHẬN DIỆN VIDEO VÀ REEL (VIDEO / REEL / WATCH / STORY)
# Tổng hợp toàn bộ các dấu hiệu nhận biết video từ cả 2 đoạn code cũ của bạn
VIDEO_URL_RE = re.compile(
    # Dạng /segment/ có hoặc không có trailing slash
    r'/(videos|reel|watch|permalink/video|video/permalink)(/|$|\?)'
    
    # watch?v= hoặc ?v= hoặc &v= (không cần slash trước)
    r'|[?&]v=\d+'
    
    # video.php?v= hoặc video_id=
    r'|video\.php'
    r'|video_id='
    
    # fb.watch và fb.com/reel shortlink
    r'|fb\.watch'
    r'|fb\.com/(reel|watch|videos)',
    
    re.IGNORECASE
)
# ════════════════════════════════════════════════════════════
#  REGEX — TIMESTAMP (NHẬN DIỆN THỜI GIAN)
# ════════════════════════════════════════════════════════════

RE_JUST_NOW   = re.compile(r'vừa xong|just now', re.I)
RE_SECONDS    = re.compile(r'\d+\s*(giây|second)', re.I)
RE_MINUTES    = re.compile(r'\d+\s*(phút|minute|min)', re.I)
RE_HOURS      = re.compile(r'(\d+)\s*(giờ|hour|hr)', re.I)
RE_TODAY      = re.compile(r'hôm\s*nay|today', re.I)
RE_YESTERDAY  = re.compile(r'hôm\s*qua|yesterday', re.I)
RE_DAYS_AGO   = re.compile(r'\d+\s*(ngày|day)', re.I)
RE_WEEKS_AGO  = re.compile(r'\d+\s*(tuần|week)', re.I)
RE_MONTHS     = re.compile(
    r'tháng|january|february|march|april|may|june|'
    r'july|august|september|october|november|december', re.I)
RE_YEAR_4D    = re.compile(r'\b(19|20)\d{2}\b')
RE_EXTRACT_TS = re.compile(
    r'(?:vào|lúc)\s+(.+?)(?:\s*$)'
    r'|đã đăng\s+(.+?)(?:\s*$)'
    r'|(\d+\s*(?:giờ|phút|giây|ngày|tuần)[^\n,;]*)',
    re.I,
)

# ════════════════════════════════════════════════════════════
#  REGEX — TƯƠNG TÁC (REACTIONS/COMMENTS/SHARES)
# ════════════════════════════════════════════════════════════
REACTION_NUM_RE = re.compile(r'([\d.,]+\s*[KkMm]?)\s*người', re.I)
NON_REACTION_KEYWORDS = re.compile(
    r'bình luận|chia sẻ|comment|share|hành động|viết|gửi|'
    r'xem ai|báo cáo|ẩn|theo dõi|lưu|sao chép|nhúng|'
    r'thông báo|bạn bè|trang cá nhân|quản trị',
    re.I,
)
COMMENT_RE = re.compile(r'([\d.,]+[KkMmTt]?)\s*bình\s*luận|bình\s*luận.*?([\d.,]+[KkMmTt]?)', re.IGNORECASE)
SHARE_RE = re.compile(
    r'([\d.,]+\s*[KkMmTtBb]?)\s*(?:lượt\s*chia\s*sẻ|chia\s*sẻ|share)'
    r'|'
    r'(?:lượt\s*chia\s*sẻ|chia\s*sẻ|share).*?([\d.,]+\s*[KkMmTtBb]?)', 
    re.IGNORECASE
)
