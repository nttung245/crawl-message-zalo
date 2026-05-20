from datetime import datetime, timedelta
import re
from app.modules.facebook.src.modules.facebook.constants.facebook_regex import (
    RE_JUST_NOW, RE_SECONDS, RE_MINUTES, RE_HOURS,
    RE_TODAY, RE_YESTERDAY, RE_DAYS_AGO, RE_WEEKS_AGO,
    RE_MONTHS, RE_YEAR_4D,
)


def extract_ts_hint(raw: str) -> str:
    """
    Trích xuất cụm từ chỉ thời gian từ raw text bất kỳ.
    Ưu tiên lấy cụm ngắn gọn nhất, đủ để classify_timestamp nhận ra.
    
    VD input:  "14 giờ · 🌐"  /  "Nguyễn Hoàng · 1 giờ"  /  "Hôm qua lúc 10:30"
    VD output: "14 giờ"        /  "1 giờ"                  /  "Hôm qua lúc 10:30"
    """
    if not raw:
        return ""

    # Thứ tự ưu tiên: từ mới nhất → cũ nhất
    ordered_patterns = [
        RE_JUST_NOW,   # vừa xong
        RE_SECONDS,    # N giây
        RE_MINUTES,    # N phút
        RE_HOURS,      # N giờ  ← "14 giờ" bắt ở đây
        RE_TODAY,      # hôm nay
        RE_YESTERDAY,  # hôm qua
        RE_DAYS_AGO,   # N ngày
        RE_WEEKS_AGO,  # N tuần
        RE_MONTHS,     # tháng / January...
        RE_YEAR_4D,    # 2024, 2025
    ]

    for pattern in ordered_patterns:
        m = pattern.search(raw)
        if m:
            return m.group(0).strip()  # Trả về đúng cụm khớp, không lấy cả raw

    return ""


def classify_timestamp(ts: str) -> str:
    """
    Phân loại timestamp thành: 'recent' | 'old' | 'unknown'
    
    - recent : trong vòng 24 giờ → lấy bài
    - old    : quá 24 giờ        → bỏ qua
    - unknown: không đọc được    → mặc định coi là recent (thà lấy dư hơn bỏ sót)
    """
    if not ts:
        return 'unknown'

    t = ts.lower().strip()

    # ── RECENT (trong 24h) ────────────────────────────────────────────────
    if RE_JUST_NOW.search(t):   return 'recent'
    if RE_SECONDS.search(t):    return 'recent'
    if RE_MINUTES.search(t):    return 'recent'
    if RE_TODAY.search(t):      return 'recent'

    # N giờ → recent nếu < 24
    m = RE_HOURS.search(t)
    if m:
        try:
            hours = int(re.search(r'\d+', m.group(0)).group())
            return 'recent' if hours < 24 else 'old'
        except Exception:
            return 'recent'  # parse lỗi → ưu tiên giữ bài

    # ── OLD (quá 24h) ─────────────────────────────────────────────────────
    if RE_YESTERDAY.search(t):  return 'old'
    if RE_DAYS_AGO.search(t):   return 'old'
    if RE_WEEKS_AGO.search(t):  return 'old'

    # Có tháng → kiểm tra thêm năm để xác định có phải năm nay không
    if RE_MONTHS.search(t):
        # Nếu có năm khác năm hiện tại → cũ chắc chắn
        m_year = RE_YEAR_4D.search(t)
        if m_year:
            try:
                year = int(m_year.group(0))
                return 'recent' if year == datetime.now().year else 'old'
            except Exception:
                pass
        return 'old'  # Có tháng nhưng không rõ năm → coi là cũ

    if RE_YEAR_4D.search(t):    return 'old'

    # ── UNKNOWN → coi là recent để không bỏ sót bài ──────────────────────
    return 'unknown'


def clean_post_url(href: str) -> str:
    """Làm sạch URL: bỏ query params rác, chỉ giữ đường dẫn gốc."""
    if not href:
        return ""
    #  nếu link bắt đc mà không có https://www.facebook.com thì thêm vào vd /reel/1377
    if href.startswith('/'):
        href = f"https://www.facebook.com{href}"
    elif not href.startswith('http'):
        href = f"https://www.facebook.com/{href}"
    try:
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
        parsed = urlparse(href)

        # 🚀 CẬP NHẬT: Thêm fbid và set để không làm hỏng link ảnh
        KEEP_PARAMS = {'story_fbid', 'id', 'v', 'video_id', 'fbid', 'set'}
        qs = parse_qs(parsed.query, keep_blank_values=False)
        filtered = {k: v for k, v in qs.items() if k in KEEP_PARAMS}

        clean = parsed._replace(
            query=urlencode(filtered, doseq=True),
            fragment=''
        )
        return urlunparse(clean)
    except Exception:
        return href