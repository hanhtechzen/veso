"""Giao diện chung cho bộ chuyển đổi nguồn dữ liệu.

Mỗi nguồn có một bộ chuyển đổi riêng: tải dữ liệu (fetch) và đọc ra các giải (parse).
Chỉ viết bộ chuyển đổi cho nguồn đã được duyệt pháp lý (cờ legal_approved).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

import httpx

from ..config import Settings


@dataclass(frozen=True)
class DrawRef:
    id: str
    game: str
    region: str
    province: str
    draw_date: date
    draw_seq: int | None = None


@dataclass
class FetchResult:
    url: str
    status: int
    body: bytes
    content_type: str = "application/octet-stream"


@dataclass
class Parsed:
    prizes: dict[str, list[str]]
    complete: bool | None = None  # None: để hệ thống tự xét theo cơ cấu giải
    meta: dict | None = None      # thông tin thêm, ví dụ {"draw_seq": 1418}


class ParseError(Exception):
    """Không nhận ra cấu trúc dữ liệu của nguồn (thường do nguồn đổi giao diện)."""


class Adapter(ABC):
    def __init__(self, code: str, config: dict, settings: Settings):
        self.code = code
        self.config = config or {}
        self.settings = settings

    @property
    def prize_map(self) -> dict[str, str]:
        return self.config.get("prize_map") or {}

    @abstractmethod
    async def fetch(self, http: httpx.AsyncClient, draw: DrawRef) -> FetchResult: ...

    @abstractmethod
    def parse(self, result: FetchResult, draw: DrawRef) -> Parsed: ...

    async def health(self, http: httpx.AsyncClient) -> None:
        """Kiểm tra nguồn còn hoạt động; mặc định gọi config['health_url'] nếu có."""
        url = self.config.get("health_url")
        if url:
            r = await http.get(url)
            r.raise_for_status()
