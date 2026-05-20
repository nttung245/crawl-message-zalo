from typing import Tuple, Optional, Dict
from app.modules.facebook.src.modules.facebook.constants.facebook_regex import POST_URL_RE, VIDEO_URL_RE,NON_REACTION_KEYWORDS, COMMENT_RE, SHARE_RE, REACTION_NUM_RE
from app.modules.facebook.src.core.utils.facebook_parsers import clean_post_url, extract_ts_hint, classify_timestamp
from app.modules.facebook.src.core.utils.date_parser import parse_interactions
from typing import List
class PostExtractor:
    """Class chuyên chịu trách nhiệm đọc hiểu các thẻ HTML/DOM của Facebook"""
    # nói chung chuyên tóc tách dữ liệu từ bài viết


    # hàm chuyên bóc tách lấy link bài viết và thời gian đăng bài viết đó 
    def get_info(element) -> Tuple[Optional[str], str]:
        """Tương tác DOM: Bóc URL và thời gian từ Element block."""
        url, post_date = None, ""
        try:
            all_links = element.locator('a[href]').all()

            # Gộp quét URL và Date vào cùng 1 vòng lặp
            for link in all_links:
                href = link.get_attribute('href') or ''
                
                # Bỏ qua nếu không phải link trỏ về bài đăng Facebook
                if '/posts/' not in href and '/permalink/' not in href:
                    continue
                if not POST_URL_RE.search(href):
                    continue
                
                candidate = clean_post_url(href)
                if candidate:
                    # Ghi nhận URL đầu tiên tìm thấy (đề phòng trường hợp thẻ này không có date)
                    if not url:
                        url = candidate
                        
                    # Bóc text (thời gian) từ CHÍNH thẻ <a> đang chứa URL này
                    raw = (link.get_attribute('aria-label') or link.inner_text() or '').strip()
                    if raw:
                        ts = extract_ts_hint(raw)
                        # Nếu ngày giờ hợp lệ, chốt hạ luôn và thoát vòng lặp
                        if classify_timestamp(ts) != 'unknown':
                            url = candidate
                            post_date = ts
                            break 

        except Exception:
            pass

        return url, post_date
    
    # hàm lấy link video nếu có
    @staticmethod
    def get_media(element, post_url: str) -> Optional[str]:
        """Tương tác DOM: Bóc tách link Video/Reel nếu có trong bài viết (Bao gồm cả bài Share)."""
        try:
            #  BƯỚC 1: Quét bề nổi - Dùng Regex tìm các link <a> hiển nhiên
            for link in element.locator('a[href]').all():
                href = link.get_attribute('href') or ''
                if VIDEO_URL_RE.search(href):
                    return clean_post_url(href)

            # BƯỚC 2:  Đào sâu bằng JS nhưng dùng Regex Python để kiểm duyệt
            if element.locator('video').count() > 0:
                
                # Dùng JS để vơ vét tất cả link tiềm năng đang bị giấu kín trong DOM
                candidate_links = element.evaluate("""
                    (el) => {
                        let links = [];
                        
                        // 1. Quét vét cạn thẻ <a> (kể cả những thẻ bị FB dùng CSS ẩn đi)
                        for (const a of el.querySelectorAll('a[href]')) {
                            links.push(a.href || a.getAttribute('href') || '');
                        }
                        
                        // 2. Mò mẫm trong các Data Attribute (Nơi FB giấu ID video)
                        for (const node of el.querySelectorAll('[data-video-id]')) {
                            const vid = node.getAttribute('data-video-id');
                            if (vid) links.push(`https://www.facebook.com/watch?v=${vid}`);
                        }
                        
                        return links;
                    }
                """)

                # Mang mảng link (candidate_links) về lại Python
                # Áp dụng ĐÚNG biến VIDEO_URL_RE để quét từng link một
                if candidate_links:
                    for href in candidate_links:
                        if VIDEO_URL_RE.search(href):
                            return clean_post_url(href)

                # BƯỚC 3: Cùng đường (có video nhưng không bóc được) - Lấy tạm link bài viết (post_url) làm link video
                return clean_post_url(post_url) if post_url else None

        except Exception:
            pass
            
        return None     
                    
    #  hàm lấy danh sách các ảnh nếu có
    @staticmethod
    def get_images(element) -> List[str]:
        """Tương tác DOM: Trích xuất danh sách các link ảnh đính kèm trong bài."""
        images = []
        try:
            # Nhắm thẳng vào thẻ <img>, không lấy thẻ <a>
            for img in element.locator('img').all():
                src = img.get_attribute('src') or ''
                
                # BỘ LỌC ẢNH RÁC:
                # 1. Ảnh thực tế của FB luôn được host trên server 'scontent'
                # 2. Loại bỏ các icon cảm xúc (thường có kích thước siêu nhỏ hoặc chứa chữ emoji/images)
                if 'scontent' in src and '/emoji/' not in src and '/images/locales/' not in src:
                    # Có thể lọc thêm bằng kích thước nếu cần (VD: chỉ lấy ảnh to)
                    width = img.get_attribute('width')
                    if width and int(width) < 100:
                        continue # Bỏ qua ảnh có chiều rộng bé hơn 100px (avatar/icon)
                        
                    images.append(src)
        except Exception:
            pass
            
        # Dùng set() để xóa các link ảnh bị trùng lặp trong cùng 1 bài, sau đó ép lại thành list
        return list(set(images))
    
   # hàm lấy các lượng tương tác , bình luận và lượt chia sẽ
   # # DEBUG: thêm tạm vào đầu hàm
        # try:
        #     for btn in element.locator('div[role="button"], span[role="button"]').all():
        #        txt = (btn.inner_text() or '').strip()
        #        if txt:
        #            print(f"[DEBUG BTN] repr={repr(txt[:80])}")
        #     for node in element.locator('[aria-label]').all():
        #          label = (node.get_attribute('aria-label') or '').strip()
        #          if label:
        #             print(f"[DEBUG ARIA] repr={repr(label[:80])}")
        # except:
        #     pass
    @staticmethod
    def get_stats(element) -> Dict[str, int]:
        from app.modules.facebook.src.core.utils.date_parser import parse_interactions
        import re
        
        reactions = 0
        comments = 0
        shares = 0
        seen_labels = set()

        # ── BƯỚC 1: QUÉT SẠCH ARIA-LABEL (Nguồn đáng tin cậy nhất cho Reactions) ──
        try:
            for node in element.locator('[aria-label]').all():
                label = (node.get_attribute('aria-label') or '').strip()
                if not label or label in seen_labels:
                    continue
                seen_labels.add(label)
                ll = label.lower()

                # Bỏ qua nhãn rác công cụ
                if NON_REACTION_KEYWORDS.search(ll):
                    continue

                # Bắt Reactions: "Thích: 3 người", "Buồn: 1 người" -> Cộng dồn
                if 'người' in ll:
                    m = REACTION_NUM_RE.search(label)
                    if m:
                        val = parse_interactions(m.group(1))
                        if val > 0:
                            reactions += val

                # Bắt Comments nếu nó tử tế ghi rõ: "15 bình luận"
                if not comments and (m := COMMENT_RE.search(label)):
                    num_str = m.group(1) or m.group(2)
                    if num_str:
                        comments = parse_interactions(num_str)

                # Bắt Shares nếu nó tử tế ghi rõ: "2 lượt chia sẻ"
                if not shares and (m := SHARE_RE.search(label)):
                    num_str = m.group(1) or m.group(2)
                    if num_str:
                        shares = parse_interactions(num_str)
        except Exception:
            pass

        # ── BƯỚC 2: QUÉT NÚT BẤM (Thu thập "Số mồ côi" trước khi chạm vùng Comment) ──
        try:
            pure_numbers = []
            action_bar_hit = False

            # Lấy cả div, span, a có role button/link
            for btn in element.locator('div[role="button"], span[role="button"], div[role="link"], a[role="link"]').all():
                txt = (btn.inner_text() or '').strip()
                if not txt:
                    continue
                
                ll = txt.lower()

                # Cờ hiệu: Nếu chạm vào các nút của thanh Action Bar, ta sẽ DỪNG việc lấy số mồ côi
                # Điều này giúp loại bỏ hoàn toàn việc bắt nhầm số lượng Like của 1 comment cụ thể
                if ll in ['thích', 'like', 'trả lời', 'reply', 'chia sẻ', 'share', 'viết bình luận']:
                    action_bar_hit = True

                # Nếu text chứa chữ rõ ràng (VD: "7 bình luận") -> Bắt luôn
                if not comments and (m := COMMENT_RE.search(txt)):
                    num_str = m.group(1) or m.group(2)
                    if num_str:
                        comments = parse_interactions(num_str)
                        continue

                if not shares and (m := SHARE_RE.search(txt)):
                    num_str = m.group(1) or m.group(2)
                    if num_str:
                        shares = parse_interactions(num_str)
                        continue

                # Nếu là "Số mồ côi" (VD: "5", "7", "1.5K") VÀ chưa chạm đến thanh Action Bar
                if not action_bar_hit and re.match(r'^[\d.,]+\s*[KkMmTtBb]?$', txt):
                    pure_numbers.append(parse_interactions(txt))

            # ── BƯỚC 3: RÁP SỐ VÀO CHỖ TRỐNG (Smart Matching) ──
            # Ví dụ pure_numbers đang là [5, 7]
            if pure_numbers:
                # Nếu Bước 1 đã đếm được reactions = 5, và số mồ côi đầu tiên cũng là 5 -> Xóa nó đi (tránh tính nhầm cho comment)
                if reactions > 0 and pure_numbers[0] == reactions:
                    pure_numbers.pop(0)
                # Nếu Bước 1 xịt, chưa có reactions -> Lấy số mồ côi đầu tiên làm reactions
                elif reactions == 0:
                    reactions = pure_numbers.pop(0)

            # Khớp các số còn lại cho Comments và Shares theo thứ tự
            if pure_numbers and comments == 0:
                comments = pure_numbers.pop(0)

            if pure_numbers and shares == 0:
                shares = pure_numbers.pop(0)

        except Exception:
            pass

        return {'reactions': reactions, 'comments': comments, 'shares': shares}
   
   # hàm  nếu thấy nội dung có nút xem thêm thì click vào nút đó 
#    và đôi khi ở phần bình luận cũng hay có nút này ta sẽ bỏ qua nó nếu ở bình luận
    @staticmethod
    def expand_see_more(element) -> None:
        """Click nút 'Xem thêm' ở nội dung chính, TUYỆT ĐỐI bỏ qua khu vực bình luận."""
        try:
            # Dùng JS để vừa tìm nút vừa kiểm tra ranh giới, tránh quét nhầm bình luận
            clicked = element.evaluate("""
                (el) => {
                    // 1. Lấy mốc ranh giới khu vực bình luận
                    const commentSection = el.querySelector(
                        '[role="article"] [role="article"], ' +
                        '[aria-label*="Comment"], ' +
                        '[aria-label*="Bình luận"], ' +
                        '[data-testid*="comment"]'
                    );
                    
                    // 2. Tìm tất cả các nút
                    const buttons = el.querySelectorAll('div[role="button"], span[role="button"]');
                    let hasClicked = false;
                    
                    for (const btn of buttons) {
                        const txt = (btn.innerText || '').trim().toLowerCase();
                        
                        // Nếu đúng là nút Xem thêm / See more
                        if (txt === 'xem thêm' || txt === 'see more') {
                            
                            // 🛡️ BỘ LỌC BÌNH LUẬN:
                            // Nếu nút nằm BÊN TRONG vùng bình luận -> Bỏ qua
                            if (commentSection && commentSection.contains(btn)) continue;
                            // Nếu nút nằm PHÍA SAU vùng bình luận -> Bỏ qua
                            if (commentSection && (commentSection.compareDocumentPosition(btn) & 4)) continue;
                            
                            // Nút nằm trong vùng bài viết chính -> Bấm!
                            btn.click();
                            hasClicked = true;
                        }
                    }
                    return hasClicked; // Trả về true nếu có bấm nút
                }
            """)
            
            # TỐI ƯU TỐC ĐỘ:
            # Chỉ cho bot nghỉ 0.5s (để chờ text bung ra) NẾU thực sự có bài viết dài cần bấm nút.
            # Nếu bài viết ngắn không có nút, bot sẽ chạy lướt qua luôn không phải chờ.
            if clicked:
                import time
                time.sleep(0.5)
                
        except Exception:
            pass
    

    #  hàm chính lấy nội dung của bài viết
    @staticmethod
    def get_content(element) -> str:
        """Tương tác DOM: Bóc tách phần Text của bài viết, TUYỆT ĐỐI không lấy bình luận"""
        PostExtractor.expand_see_more(element)
        #  TẦNG 1: Dùng chìa khóa chuẩn (Ưu tiên lấy chuẩn xác và nhanh nhất)
        try:
            for selector in [
                'div[data-ad-comet-preview="message"]', 
                'div[data-ad-preview="message"]'
            ]:
                node = element.locator(selector).first
                if node.count() > 0:
                    return node.inner_text().strip()
        except Exception:
            pass

        #  TẦNG 2: Fallback bằng JS Evaluate (Lọc chính xác theo vị trí DOM)
        # Quét div[dir="auto"] nhưng dừng lại ngay khi chạm mặt vùng Bình Luận
        try:
            content = element.evaluate("""
                (el) => {
                    // 1. Tìm cái mốc ranh giới: Khu vực bình luận hoặc thanh reaction
                    const commentSection = el.querySelector(
                        '[role="article"] [role="article"], ' +  // Bài viết lồng trong bài viết = comment
                        '[aria-label*="Comment"], ' +
                        '[aria-label*="Bình luận"], ' +
                        '[data-testid*="comment"]'
                    );
                    
                    // 2. Tìm tất cả các khối chứa chữ
                    const allDirs = el.querySelectorAll('div[dir="auto"]');
                    let bestText = '';
                    
                    // Từ khóa UI cấm kỵ (giống NON_REACTION_KEYWORDS ở Python)
                    const banWords = ['bình luận', 'chia sẻ', 'comment', 'share', 'thông báo'];
                    
                    for (const div of allDirs) {
                        // NẾU thẻ này nằm BÊN TRONG commentSection -> Bỏ qua
                        if (commentSection && commentSection.contains(div)) {
                            continue;
                        }
                        
                        // NẾU thẻ này nằm PHÍA SAU commentSection -> Bỏ qua
                        // (Dùng cờ 4: Node.DOCUMENT_POSITION_FOLLOWING)
                        if (commentSection && (commentSection.compareDocumentPosition(div) & 4)) {
                            continue;
                        }
                        
                        const txt = (div.innerText || '').trim();
                        const txtLower = txt.toLowerCase();
                        
                        // Lọc rác: Bỏ qua text quá ngắn hoặc chứa từ khóa UI
                        const isBanned = banWords.some(word => txtLower.includes(word));
                        
                        if (txt.length > 20 && !isBanned) {
                            // Cập nhật lấy đoạn text dài nhất (Caption bài viết)
                            if (txt.length > bestText.length) {
                                bestText = txt;
                            }
                        }
                    }
                    return bestText;
                }
            """)
            if content:
                return content.strip()
        except Exception:
            pass
            
        return ""