"""Coordinate outer chapter retries with retrying provider implementations."""

from contextlib import contextmanager
from contextvars import ContextVar


_chapter_retry_managed = ContextVar("chapter_retry_managed", default=False)


def chapter_retry_managed():
    """Return whether the current call belongs to a managed chapter attempt."""
    return _chapter_retry_managed.get()


@contextmanager
def managed_chapter_attempt():
    """Make inner layers propagate errors to the chapter-level retry loop."""
    token = _chapter_retry_managed.set(True)
    try:
        yield
    finally:
        _chapter_retry_managed.reset(token)
