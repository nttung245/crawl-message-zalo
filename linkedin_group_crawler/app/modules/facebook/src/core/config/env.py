import os
from dotenv import load_dotenv

load_dotenv()

class Config:
   
    GROUP_URL = os.getenv("FB_GROUP_URL")
    STATE_PATH = "facebook_state.json"
    OUTPUT_FILE = "fb_posts_final.txt"
    OUTPUT_FILE_HOT = "fb_post_hot.txt"
    SCROLL_ATTEMPTS = int(os.getenv("SCROLL_ATTEMPTS", 15))
    SCROLL_DISTANCE = 2000     
     # Số pixel cuộn chuột mỗi lần
    SCROLL_SLEEP_MIN = 1.5     
     # Thời gian nghỉ tối thiểu sau khi cuộn (giây)
    SCROLL_SLEEP_MAX = 4.0     
     # Thời gian nghỉ tối đa sau khi cuộn (giây)
    MAX_OLD_POSTS_LIMIT = 5    
     # Ngưỡng bài cũ liên tiếp để dừng tool
    SAFE_LIMIT=100             
       # ngưỡng bài viết tối đa để ngừng nếu không nó sẽ lấy mãi nếu có các bài viết hợp lệ 
    #  trang đăng nhập nếu chưa lấy cookie
    # Tìm đến các ô để nhập dữ liệu login
      # ô email
    AUTH_SELECTORS = {
        "email": 'input[name="email"]',
        "password": 'input[name="pass"]'
    }
   
    # thẻ bài viết
    DEFAULT_FB_EMAIL = os.getenv("FB_EMAIL")
    DEFAULT_FB_PASSWORD = os.getenv("FB_PASSWORD")
    DEFAULT_FB_2FA = os.getenv("FB_2FA_SECRET")
    
    # Thẻ bao quanh toàn bộ 1 bài viết (thường là div con trực tiếp của feed)
    FB_POST_CONTAINER = 'div[role="feed"] > div, div[data-testid="fbfeed_story"]'

    # Thẻ chứa nội dung text chính
    FB_POST_CONTENT = 'div[data-ad-comet-preview="message"]'

     # Thẻ chứa link timestamp/URL
    FB_POST_LINK = 'a[role="link"][target="_blank"]'

    
    #  gg sheet
    GOOGLE_CREDENTIALS_PATH=os.getenv("GOOGLE_CREDENTIALS_PATH")
    SPREADSHEET_ID=os.getenv("SPREADSHEET_ID")
    


    GOOGLE_SHEET_NAME_APPEND=os.getenv("GOOGLE_SHEET_NAME_APPEND")
    LINK_GGSHEET=os.getenv("LINK_GGSHEET")


    # Cấu hình giờ mặt định để chạy mỗi ngày
    CRAWL_HOUR=10
       # giờ chạy
    CRAWL_MINUTE=16
       # phút chạy
    # Cấu hình giờ mặt định để chạy mỗi ngày
    GROUP_HOUR=2
       # giờ chạy
    GROUP_MINUTE=20
       # phút chạy


    # cấu hình cho telegram
    TELEGRAM_TOKEN=os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID=os.getenv("TELEGRAM_CHAT_ID")
    TELEGRAM_TOPIC_ID=os.getenv("TELEGRAM_TOPIC_ID")
    TELEGRAM_TOPIC_CHAT_ID=os.getenv("TELEGRAM_TOPIC_CHAT_ID")

   #  tài khoản mặc định để đăng nhập vào facebook nếu không có cookie nào hợp lệ, bạn có thể thêm nhiều tài khoản vào Google Sheet và tool sẽ tự động lấy để đăng nhập luân phiên tránh bị checkpoint
    GOOGLE_SHEET_EMAIL_DEFAULT = os.getenv("GOOGLE_SHEET_EMAIL_DEFAULT", "")
    GOOGLE_SHEET_PASSWORD_DEFAULT = os.getenv("GOOGLE_SHEET_PASSWORD_DEFAULT", "")
    GOOGLE_SHEET_2FA_DEFAULT = os.getenv("GOOGLE_SHEET_2FA_DEFAULT", "")
    GOOGLE_SHEET_NAME_DEFAULT = os.getenv("GOOGLE_SHEET_NAME_DEFAULT", "Account Default")
   #  cào tự động 24h
    GOOGLE_SHEET_NAME_24H = os.getenv("GOOGLE_SHEET_NAME_24H")
    NAME_URL_GG_SHEET_24H = os.getenv("NAME_URL_GG_SHEET_24H")
    NAME_GROUP_GG_SHEET_24H = os.getenv("NAME_GROUP_GG_SHEET_24H")
    INTENT_GG_SHEET_24H = os.getenv("INTENT_GG_SHEET_24H")
    
    GOOGLE_SHEET_NAME_GROUPS=os.getenv("GOOGLE_SHEET_NAME_GROUPS")
    NAME_GROUP_GG_SHEET = os.getenv("NAME_GROUP_GG_SHEET")
    NAME_URL_GG_SHEET = os.getenv("NAME_URL_GG_SHEET")
    INTENT_GG_SHEET = os.getenv("INTENT_GG_SHEET")
    MEMBERS_GG_SHEET = os.getenv("MEMBERS_GG_SHEET")
    POSTS_PER_WEEK_GG_SHEET = os.getenv("POSTS_PER_WEEK_GG_SHEET")
    LAST_CRAWL_GG_SHEET = os.getenv("LAST_CRAWL_GG_SHEET")
    HEALTH_SCORE_GG_SHEET = os.getenv("HEALTH_SCORE_GG_SHEET")


   
    CRAWL_DATE_GG_SHEET_POST = os.getenv("CRAWL_DATE_GG_SHEET_POST")
    NAME_GROUP_GG_SHEET_POST = os.getenv("NAME_GROUP_GG_SHEET_POST")
    LINK_GROUP_GG_SHEET_POST = os.getenv("LINK_GROUP_GG_SHEET_POST")
    INTENT_GG_SHEET_POST = os.getenv("INTENT_GG_SHEET_POST")
    TOTAL_POSTS_GG_SHEET_POST = os.getenv("TOTAL_POSTS_GG_SHEET_POST")
    LINK_POST_GG_SHEET_POST = os.getenv("LINK_POST_GG_SHEET_POST")
    POST_TIME_GG_SHEET_POST = os.getenv("POST_TIME_GG_SHEET_POST")
    CONTENT_GG_SHEET_POST = os.getenv("CONTENT_GG_SHEET_POST")
    SCORE_GG_SHEET_POST = os.getenv("SCORE_GG_SHEET_POST")
    LIKES_GG_SHEET_POST = os.getenv("LIKES_GG_SHEET_POST")
    COMMENTS_GG_SHEET_POST = os.getenv("COMMENTS_GG_SHEET_POST")
    SHARES_GG_SHEET_POST = os.getenv("SHARES_GG_SHEET_POST")
    LINK_VIDEO_GG_SHEET_POST = os.getenv("LINK_VIDEO_GG_SHEET_POST")
    LINK_IMAGE_GG_SHEET_POST = os.getenv("LINK_IMAGE_GG_SHEET_POST")
    CHAY_24H_GG_SHEET_POST=os.getenv("CHAY_24H_GG_SHEET_POST")
    GOOGLE_SHEET_NAME_POST=os.getenv("GOOGLE_SHEET_NAME_POST")
   #  các loại INTENTS
    VALUE_GG_SHEET_INTENTS = os.getenv("VALUE_GG_SHEET_INTENTS")
    NAME_GG_SHEET_INTENTS = os.getenv("NAME_GG_SHEET_INTENTS")
    GOOGLE_SHEET_NAME_INTENTS = os.getenv("GOOGLE_SHEET_NAME_INTENTS")
    

    ## cấu hình cho user score
    GOOGLE_SHEET_NAME_USERS = os.getenv("GOOGLE_SHEET_NAME_USERS")
    USER_COMMENT_HEADER_ID = os.getenv("USER_COMMENT_HEADER_ID")
    USER_COMMENT_HEADER_NAME = os.getenv("USER_COMMENT_HEADER_NAME")
    USER_COMMENT_HEADER_SCORE_WEEK = os.getenv("USER_COMMENT_HEADER_SCORE_WEEK")
    
    # cấu hình cho user comment
    GOOGLE_SHEET_NAME_COMMENTS = os.getenv("GOOGLE_SHEET_NAME_COMMENTS")
    COMMENT_HEADER_ID = os.getenv("COMMENT_HEADER_ID")
    COMMENT_HEADER_URL_POST = os.getenv("COMMENT_HEADER_URL_POST")
    COMMENT_HEADER_NAME = os.getenv("COMMENT_HEADER_NAME")
    COMMENT_HEADER_LIKE = os.getenv("COMMENT_HEADER_LIKE")
    COMMENT_HEADER_COMMENT = os.getenv("COMMENT_HEADER_COMMENT")
    COMMENT_HEADER_DATE_COMMENT = os.getenv("COMMENT_HEADER_DATE_COMMENT")
    # Cấu hình Google Sheet Lịch sử (Lưu lại trước khi reset)
    GOOGLE_SHEET_NAME_HISTORY = os.getenv("GOOGLE_SHEET_NAME_HISTORY")
    HISTORY_HEADER_ID = os.getenv("HISTORY_HEADER_ID")
    HISTORY_HEADER_NAME = os.getenv("HISTORY_HEADER_NAME")
    HISTORY_HEADER_SCORE_WEEK = os.getenv("HISTORY_HEADER_SCORE_WEEK")
    HISTORY_HEADER_DATE_PER_WEEK = os.getenv("HISTORY_HEADER_DATE_PER_WEEK")

    #
    
    COOKIE_DIR = "app/modules/facebook/src/storages/sessions"
    OTP_DIR = "app/modules/facebook/src/storages/tem_otp"
    NGROK_AUTH_TOKEN=os.getenv("NGROK_AUTH_TOKEN")