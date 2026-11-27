"""Tài nguyên dùng chung của bộ thu thập."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx

from ..config import Settings


class SourceGate:
    """Giới hạn tần suất và ngắt tạm (circuit breaker) theo từng nguồn."""

    def __init__(self, max_failures: int = 5, cooldown_s: float = 600):
        self.max_failures = max_failures
        self.cooldown_s = cooldown_s
        self._last: dict[str, float] = {}
        self._fails: dict[str, int] = {}
        self._open_until: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def is_open(self, code: str) -> bool:
        return time.monotonic() < self._open_until.get(code, 0)

    async def wait_turn(self, code: str, rate_limit_ms: int) -> None:
        lock = self._locks.setdefault(code, asyncio.Lock())
        async with lock:
            gap = rate_limit_ms / 1000 - (time.monotonic() - self._last.get(code, 0))
            if gap > 0:
                await asyncio.sleep(gap)
            self._last[code] = time.monotonic()

    def success(self, code: str) -> None:
        self._fails[code] = 0

    def failure(self, code: str) -> bool:
        """Ghi nhận một lần lỗi. Trả về True nếu nguồn vừa bị ngắt tạm."""
        n = self._fails.get(code, 0) + 1
        self._fails[code] = n
        if n >= self.max_failures:
            self._open_until[code] = time.monotonic() + self.cooldown_s
            self._fails[code] = 0
            return True
        return False


@dataclass
class Ctx:
    settings: Settings
    pool: object
    http: httpx.AsyncClient
    gate: SourceGate = field(default_factory=SourceGate)
    alerts: list[tuple[str, str]] = field(default_factory=list)  # (mức, nội dung) chờ gửi


def make_http(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=settings.http_timeout_s, follow_redirects=True,
                             headers={"User-Agent": settings.user_agent})
