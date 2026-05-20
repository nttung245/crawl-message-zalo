import random
import time
import math
from playwright.sync_api import Page

class HumanBehavior:
    @staticmethod
    def gamma_delay(mean: float = 1.0, shape: float = 2.0) -> None:
        """Delay với phân phối Gamma (lệch phải giống con người)."""
        delay = random.gammavariate(shape, mean / shape)
        time.sleep(min(delay, 10))  # crop tránh quá lâu

    @staticmethod
    def move_mouse_like_human(page: Page, x1: int, y1: int, x2: int, y2: int):
        """Di chuột theo đường cong Bezier với vận tốc tự nhiên."""
        steps = random.randint(30, 60)
        cp1x = x1 + random.randint(-100, 100)
        cp1y = y1 + random.randint(-100, 100)
        cp2x = x2 + random.randint(-100, 100)
        cp2y = y2 + random.randint(-100, 100)

        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier
            x = (1-t)**3 * x1 + 3*(1-t)**2 * t * cp1x + 3*(1-t) * t**2 * cp2x + t**3 * x2
            y = (1-t)**3 * y1 + 3*(1-t)**2 * t * cp1y + 3*(1-t) * t**2 * cp2y + t**3 * y2
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.005, 0.02))

    @staticmethod
    def random_scroll(page: Page, max_distance: int = 400):
        """Cuộn xuống một khoảng ngẫu nhiên, thỉnh thoảng cuộn lên."""
        direction = random.choice([1, 1, 1, 1])  # 25% cuộn lên
        distance = random.randint(50, max_distance) * direction
        page.mouse.wheel(0, distance)
        HumanBehavior.gamma_delay(mean=0.8, shape=2)

    @staticmethod
    def act_like_reading(page: Page):
        """Tạm dừng, di chuột lung tung, giả vờ đọc."""
        w, h = page.viewport_size["width"], page.viewport_size["height"]
        for _ in range(random.randint(1, 3)):
            x = random.randint(w//4, 3*w//4)
            y = random.randint(h//4, 3*h//4)
            HumanBehavior.move_mouse_like_human(page, w//2, h//2, x, y)
            HumanBehavior.gamma_delay(mean=1.5, shape=3)