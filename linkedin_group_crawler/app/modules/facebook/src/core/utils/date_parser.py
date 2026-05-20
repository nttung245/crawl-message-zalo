import re
_PI_RE = re.compile(
    r'(\d[\d.]*)(?:[,.](\d+))?\s*([KkMmTt])(?!\w)'   # nhánh có suffix
    r'|'
    r'(\d[\d.]*)(?:[,.](\d+))?',                       # nhánh không suffix
)
_MULT = {'k': 1_000, 't': 1_000, 'm': 1_000_000}
 
 
def parse_interactions(raw: str) -> int:
    """
    Chuyển chuỗi tương tác Facebook → số nguyên.
 
    Format hỗ trợ:
        "177"                → 177
        "1.2K" / "1,2K"     → 1 200
        "1.200"              → 1 200   ← dấu chấm nghìn kiểu VN
        "12.500"             → 12 500
        "2.5M"               → 2 500 000
        "1.200 người"        → 1 200   ← chuỗi reaction
        "177 bình luận"      → 177     ← 'b' trong "bình" KHÔNG bị bắt thành Billion
        "" / None            → 0
    """
    if not raw:
        return 0
    m = _PI_RE.search(raw.strip())
    if not m:
        return 0
 
    # Nhánh 1 (có suffix, group 1-3) hoặc nhánh 2 (không suffix, group 4-5)
    if m.group(1) is not None:
        int_raw, dec, sfx = m.group(1), m.group(2), m.group(3)
    else:
        int_raw, dec, sfx = m.group(4), m.group(5), None
 
    mult = _MULT.get((sfx or '').lower(), 1)
 
    # Phân biệt dấu chấm nghìn vs thập phân:
    #   Có suffix + dấu chấm → "1.2K" = thập phân
    #   Không suffix + dấu chấm → "1.200" = phân cách nghìn VN
    if '.' in int_raw:
        if mult > 1:
            parts = int_raw.split('.')
            int_raw = parts[0]
            if len(parts) > 1:
                dec = parts[1]
        else:
            int_raw = int_raw.replace('.', '')
            dec = None
 
    val = int(int_raw)
    if dec and mult > 1:
        val = (val + int(dec) / 10 ** len(dec)) * mult
    else:
        val = val * mult
 
    return int(val)