import asyncio


# A single Zalo browser page cannot safely handle crawl, group discovery,
# verification, and broadcast at the same time. All operations that navigate
# or inspect chat.zalo.me should use this lock before touching the page.
zalo_browser_operation_lock = asyncio.Lock()
