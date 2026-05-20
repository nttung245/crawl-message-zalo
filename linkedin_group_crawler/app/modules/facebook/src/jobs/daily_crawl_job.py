import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta

# THAY ĐỔI: Sử dụng AsyncIOScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.asyncio import AsyncIOExecutor

# Import các service
from app.modules.facebook.src.modules.gg_sheet.services.google_sheets_groups_24h import TargetGroupSheet24HService
from app.modules.facebook.src.modules.gg_sheet.services.google_sheets_posts import GoogleSheetServicePosts
from app.modules.facebook.src.modules.gg_sheet.services.google_sheets_groups_service import GroupManagementSheetService

from app.modules.facebook.src.modules.gg_sheet.services.history_sheet_service import HistorySheetService
from app.modules.facebook.src.modules.gg_sheet.services.user_score_sheet_service import UserScoreSheetService
from app.modules.facebook.src.modules.facebook.services.facebook_scraper import FacebookScraper, GroupTarget
from app.modules.facebook.src.modules.telegram.services.telegram_service import TelegramService
from app.modules.facebook.src.core.config.env import Config
from app.modules.facebook.src.modules.crawl_fb.models.GroupSummary import GroupSummary




logger = logging.getLogger(__name__)

def execute_crawl_workflow():
    """
    Luồng công việc thực tế cào dữ liệu và báo cáo.
    """
    logger.info("🚀 BẮT ĐẦU CHẠY TIẾN TRÌNH CÀO DỮ LIỆU TỰ ĐỘNG...")
    telegram = TelegramService()
    service_24h = TargetGroupSheet24HService()
    service_posts = GoogleSheetServicePosts()
    
    try:
        
        sheet_data = service_24h.get_all_target_groups()
        print(f"🚀 Lấy dữ liệu nhóm mục tiêu từ Google Sheet 24h: {sheet_data} nhóm")
        target_groups: List[GroupTarget] = []
        for row in sheet_data:
            
            group_url = row.get("url", "").strip()
            group_name = row.get("group_name", "Unknown").strip()
            Intent = row.get("intent", "").strip()
            if not group_url: continue
            target_groups.append(GroupTarget(name=group_name, url=group_url,Intent=Intent or ""))

        if not target_groups:
            logger.warning("❌ Không tìm thấy danh sách Group hợp lệ.")
            return

        # 3. Bắt đầu cào
        logger.info(f"Tổng cộng có {len(target_groups)} group cần cào.")
        scraper = FacebookScraper(Config)
        daily_summary_report: List[GroupSummary] = scraper.scrape_groups(target_groups)

        # 4. Gửi báo cáo
        if daily_summary_report:
            success = service_posts.append_data(data=daily_summary_report)
            if success:
                telegram.send_completion_notification()
                mes = telegram.format_daily_telegram_report(summaries=daily_summary_report)
                telegram.send_message(mes)
                logger.info("✅ HOÀN TẤT TIẾN TRÌNH.")
            else:
                logger.error("❌ Lỗi khi lưu dữ liệu vào Google Sheet.")
        else:
            logger.warning("⚠️ Không thu được dữ liệu.")

    except Exception as e:
        logger.error(f"❌ Thất bại: {e}", exc_info=True)
        try:
            # FIX 2: Thêm 'await' khi gửi tin báo lỗi trong block except
             telegram.send_message(f"🚨 <b>LỖI HỆ THỐNG</b> 🚨\n\n<code>{str(e)}</code>")
        except: 
            pass
def execute_update_groups_workflow():
    """
    Luồng công việc tổng hợp chỉ số (Post/tuần, Điểm số cao nhất và Ngày cào gần nhất) 
    từ danh sách Posts và cập nhật lại vào sheet Groups.
    """
    logger.info("📊 BẮT ĐẦU TỔNG HỢP VÀ CẬP NHẬT CHỈ SỐ GROUPS...")
    service_posts = GoogleSheetServicePosts()
    service_groups = GroupManagementSheetService()
    telegram = TelegramService()

    try:
        # 1. Lấy toàn bộ bài viết đã lưu
        all_posts = service_posts.get_all_posts()
        if not all_posts:
            logger.warning("⚠️ Không có dữ liệu bài viết để tổng hợp chỉ số.")
            return

        # 2. Phân tích và gom nhóm theo URL Group
        group_metrics: Dict[str, Dict[str, Any]] = {}
        seven_days_ago = datetime.now() - timedelta(days=7)

        for post in all_posts:
            group_url = post.get("link_group", "").strip()
            if not group_url:
                continue

            score = post.get("score", 0)
            crawl_date_str = post.get("dateCrawl", "").strip()

            # Khởi tạo dữ liệu cho Group nếu chưa tồn tại
            if group_url not in group_metrics:
                group_metrics[group_url] = {
                    "max_score": 0.0,
                    "posts_last_7d": 0,
                    "last_crawl": "" # <--- THÊM MỚI
                }

            # Cập nhật điểm số cao nhất
            if score > group_metrics[group_url]["max_score"]:
                group_metrics[group_url]["max_score"] = float(score)

            # Xử lý ngày tháng để đếm bài viết 7 ngày và tìm ngày cào gần nhất
            if crawl_date_str:
                try:
                    crawl_date = datetime.strptime(crawl_date_str, "%Y-%m-%d %H:%M:%S")
                    
                    # Cập nhật ngày cào gần nhất (So sánh chuỗi hoặc datetime)
                    # Nếu last_crawl trống hoặc ngày hiện tại mới hơn ngày đã lưu
                    current_last_crawl_str = group_metrics[group_url]["last_crawl"]
                    if not current_last_crawl_str or crawl_date_str > current_last_crawl_str:
                        group_metrics[group_url]["last_crawl"] = crawl_date_str

                    # Đếm số bài trong 7 ngày qua
                    if crawl_date >= seven_days_ago:
                        group_metrics[group_url]["posts_last_7d"] += 1
                except Exception:
                    # Nếu lỗi định dạng ngày, vẫn tính là 1 post nhưng không cập nhật last_crawl
                    group_metrics[group_url]["posts_last_7d"] += 1
            else:
                group_metrics[group_url]["posts_last_7d"] += 1

        # 3. Thực thi cập nhật từng Group trên Sheet
        logger.info(f"🔄 Bắt đầu cập nhật dữ liệu cho {len(group_metrics)} Groups...")
        success_count = 0

        for group_url, metrics in group_metrics.items():
            # Chuẩn bị payload cập nhật
            update_payload = {
                Config.POSTS_PER_WEEK_GG_SHEET: metrics["posts_last_7d"],
                Config.HEALTH_SCORE_GG_SHEET: metrics["max_score"],
                Config.LAST_CRAWL_GG_SHEET: metrics["last_crawl"] # <--- THÊM MỚI
            }
            
            is_updated = service_groups.update_group_metrics(
                group_url=group_url, 
                update_data=update_payload
            )
            if is_updated:
                success_count += 1

        logger.info(f"✅ HOÀN TẤT CẬP NHẬT CHỈ SỐ GROUPS. Thành công: {success_count}/{len(group_metrics)}")

    except Exception as e:
        logger.error(f"❌ Thất bại khi cập nhật chỉ số Groups: {e}", exc_info=True)

# ==============================================================================
# ✅ LUỒNG TÁC VỤ 3 THÊM MỚI: BACKUP VÀ RESET ĐIỂM SỐ HÀNG TUẦN (CHỦ NHẬT 2:00 AM)
# ==============================================================================
async def execute_weekly_backup_and_reset_workflow():
    """
    Tác vụ chạy ngầm hàng tuần:
    1. Đọc toàn bộ bảng User_Scores.
    2. Chuyển đổi DTO và đẩy sang bảng History.
    3. Reset toàn bộ điểm tuần về 0 cho bảng User_Scores cũ.
    """
    logger.info("📅 [WEEKLY JOB] BẮT ĐẦU QUY TRÌNH SAO LƯU VÀ RESET ĐIỂM TUẦN...")
    telegram = TelegramService()
    user_score_service = UserScoreSheetService()
    history_service = HistorySheetService()

    try:
        # 1. Đọc bảng điểm số hiện tại (Chạy trên Threadpool để tránh block Event Loop)
        user_scores: List[Dict[str, Any]] = await asyncio.to_thread(user_score_service.get_all_user_scores)
        
        if not user_scores:
            logger.warning("⚠️ Bảng điểm User_Scores trống hoặc không đọc được dữ liệu. Hủy quy trình backup.")
            return

        current_date_str = datetime.now().strftime("%Y-%m-%d")
        records_to_backup: List[Dict[str, str]] = []

        # 2. Ánh xạ (Mapping) cấu trúc header từ bảng điểm cũ sang cấu trúc lịch sử mới
        for row in user_scores:
            uid = row.get(Config.USER_COMMENT_HEADER_ID)
            name = row.get(Config.USER_COMMENT_HEADER_NAME)
            score = row.get(Config.USER_COMMENT_HEADER_SCORE_WEEK)

            if uid:
                records_to_backup.append({
                    "id": str(uid).strip(),
                    "name": str(name).strip(),
                    "score": str(score if score is not None else 0).strip(),
                    "date": current_date_str
                })

        if not records_to_backup:
            logger.warning("⚠️ Không tìm thấy bản ghi hợp lệ nào để sao lưu.")
            return

        # 3. Thực hiện Bulk Insert vào sheet History
        logger.info(f"📦 Đang sao lưu {len(records_to_backup)} bản ghi thành viên sang Sheet Lịch sử...")
        backup_success = await asyncio.to_thread(
            history_service.add_multiple_histories, 
            records_to_backup
        )

        if not backup_success:
            raise RuntimeError("Lỗi hệ thống khi đẩy dữ liệu lên Google Sheet History.")

        # 4. Sau khi backup thành công tuyệt đối -> Thực hiện reset điểm số về 0
        logger.info("🔄 Đang dọn dẹp và reset cột điểm tuần về 0...")
        reset_success = await asyncio.to_thread(user_score_service.reset_all_scores_to_zero)

        if reset_success:
            logger.info("✅ HOÀN TẤT CHU KỲ TUẦN. Đã sao lưu dữ liệu và đưa toàn bộ điểm về 0.")
            # Báo cáo trạng thái tốt qua Telegram channel
            telegram.send_message(
                f"📊 <b>BÁO CÁO CUỐI TUẦN</b> 📊\n\n"
                f"✅ Đã sao lưu thành công <code>{len(records_to_backup)}</code> tài khoản sang lịch sử.\n"
                f"🔄 Đã đưa toàn bộ điểm số tuần về 0."
            )
        else:
            logger.error("❌ Sao lưu thành công nhưng lệnh RESET điểm số về 0 thất bại.")

    except Exception as e:
        logger.error(f"❌ Thất bại trong quy trình xử lý cuối tuần: {e}", exc_info=True)
        try:
            telegram.send_message(f"🚨 <b>LỖI HỆ THỐNG CRON WEEKLY</b> 🚨\n\n<code>{str(e)}</code>")
        except Exception:
            pass
        
def setup_and_start_jobs():
    """
    Khởi tạo scheduler theo phong cách Async chuẩn Product.
    """
    # 1. Cấu hình Executor cho phép chạy Async
    executors = {
        'default': AsyncIOExecutor()
    }

    # 2. Khởi tạo AsyncIOScheduler thay vì BackgroundScheduler
    scheduler = AsyncIOScheduler(executors=executors)

    # 3. Thêm công việc vào lịch
    scheduler.add_job(
        func=execute_crawl_workflow,
        trigger='cron',
        hour=Config.CRAWL_HOUR,
        minute=Config.CRAWL_MINUTE,
        id='daily_facebook_crawl',
        replace_existing=True
    )
    scheduler.add_job(
        func=execute_update_groups_workflow,
        trigger='cron',
        hour=Config.GROUP_HOUR,
        minute=Config.GROUP_MINUTE,
        id='daily_facebook_UPDATE_GROUP',
        replace_existing=True
    )
    scheduler.add_job(
        func=execute_weekly_backup_and_reset_workflow,
        trigger='cron',
        day_of_week='sun', # Thực thi vào Chủ nhật
        hour=2,            # Lúc 2 giờ sáng
        minute=0,          # 00 phút
        id='weekly_user_score_backup_reset',
        replace_existing=True
    )

    logger.info(f"🕒 Scheduler khởi động (Chế độ: AsyncIO). Lịch: {Config.CRAWL_HOUR}:{Config.CRAWL_MINUTE:02d}")
    
    # Bắt đầu bộ đếm thời gian
    scheduler.start()