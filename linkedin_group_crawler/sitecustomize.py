"""Windows asyncio policy bootstrap for Playwright subprocess support."""

from __future__ import annotations

import asyncio
import sys


if sys.platform == "win32":
    policy = asyncio.get_event_loop_policy()
    if not isinstance(policy, asyncio.WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
