import functools
import logging
import time
from collections.abc import Awaitable, Callable

logger = logging.getLogger("airq.timing")


def log_duration[T, **P](func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    # Must be applied before router.get() runs, i.e. written below it in the
    # decorator stack (decorators apply bottom-up) — doesn't need to sit
    # directly adjacent to the function, just closer to it than router.get().
    # Reversed, `router.get()` captures the raw function first and Starlette
    # keeps calling that reference forever; wrapping it afterwards only
    # rebinds a name nothing looks up again (see tests/test_decorator_placement.py).
    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        started_at = time.perf_counter()
        outcome = "ok"
        try:
            return await func(*args, **kwargs)
        except BaseException:
            outcome = "error"
            raise
        finally:
            # finally so a raised exception still gets timed instead of
            # silently skipping the log line.
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.info("%s took %.1fms (%s)", func.__name__, elapsed_ms, outcome)

    return wrapper
