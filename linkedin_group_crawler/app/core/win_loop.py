from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable


def proactor_loop_factory(use_subprocess: bool = False) -> Callable[[], asyncio.AbstractEventLoop]:
    """Return a Windows Proactor loop so subprocess-based browsers work.

    Uvicorn defaults to a selector loop on Windows when subprocess support is
    involved. Playwright needs subprocess support, so we force Proactor here.
    """

    if sys.platform == "win32":
        return asyncio.ProactorEventLoop
    return asyncio.SelectorEventLoop
