"""Lớp chung cho các bộ cào trang web: giới hạn lịch sự, robots.txt, nhận diện bị chặn."""
from __future__ import annotations

import httpx

from .base import Adapter
from .html_util import ROBOTS, SourceBlocked

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class ScrapeAdapter(Adapter):
    """Cấu hình chung (data_sources.config):
      respect_robots: true   tôn trọng robots.txt (mặc định bật)
      user_agent: "..."      mặc định dùng User-Agent của LuckyVision; có thể đổi
    """

    @property
    def user_agent(self) -> str:
        ua = self.config.get("user_agent") or self.settings.user_agent
        return BROWSER_UA if ua == "browser" else ua

    def headers(self, extra: dict | None = None) -> dict:
        h = {"User-Agent": self.user_agent, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.5"}
        h.update(extra or {})
        return h

    async def guard(self, http: httpx.AsyncClient, url: str) -> None:
        if self.config.get("respect_robots", True) and not await ROBOTS.allowed(http, url, self.user_agent):
            raise SourceBlocked(f"robots.txt của trang không cho phép tải {url}")

    @staticmethod
    def check_blocked(r: httpx.Response) -> None:
        if r.status_code in (403, 429, 503) and (
                "cloudflare" in r.headers.get("server", "").lower() or "cf-ray" in r.headers
                or "captcha" in r.text[:5000].lower()):
            raise SourceBlocked(f"Trang chặn truy cập tự động (HTTP {r.status_code}). Hãy dùng nguồn khác.")
