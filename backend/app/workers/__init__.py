"""Worker utilities."""
import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

_worker_loop: asyncio.AbstractEventLoop | None = None


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run async code on a per-process event loop reused across Celery tasks."""
    global _worker_loop

    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)

    return _worker_loop.run_until_complete(coro)


__all__ = ["run_async"]
