from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Callable

_LOGGER = logging.getLogger(__name__)


class TaskQueue:
    def __init__(self, max_workers: int) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, func: Callable[..., None], *args, **kwargs) -> None:
        future = self._executor.submit(func, *args, **kwargs)
        future.add_done_callback(_log_task_result)


def _log_task_result(future) -> None:
    try:
        future.result()
    except Exception:
        _LOGGER.exception("Background task failed")
