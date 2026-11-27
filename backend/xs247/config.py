"""Cấu hình đọc từ biến môi trường (tệp .env)."""
from __future__ import annotations

from typing import ClassVar

from dataclasses import dataclass
from datetime import time
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"  # dev | prod
    database_url: str = "postgresql://luckey:luckey@db:5432/luckey"
    redis_url: str = "redis://redis:6379/0"
    raw_dir: str = "/data/raw"
    fixture_dir: str = "/app/fixtures"

    # Tự xác minh khi hai nguồn độc lập khớp nhau (xem mục 4 tài liệu thiết kế)
    auto_verify: bool = True
    min_matching_sources: int = 2
    # Số nguồn cần khớp theo từng miền, ví dụ "vl:1,mn:2,mb:2". Miền không ghi dùng min_matching_sources.
    min_sources_by_region: str = "vl:1"

    # Quản trị: danh sách "token:vai_trò:tên", cách nhau bằng dấu phẩy
    admin_tokens: str = ""

    # Cảnh báo
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    slack_webhook_url: str = ""
    healthchecks_url: str = ""
    sentry_dsn: str = ""

    # Trang công khai cho SEO: địa chỉ chính thức (không có dấu / cuối), dùng cho canonical và sitemap
    site_url: str = "http://localhost"
    site_name: str = "XS247"
    # Liên hệ công khai (chân trang, trang Liên hệ, dữ liệu có cấu trúc)
    contact_phone: str = "0865 556 800"
    contact_email: str = "nguyenhanh7654@gmail.com"
    # Cách người dùng liên hệ quản trị khi quên mật khẩu, hiện trên trang đăng nhập; để trống thì dùng mặc định bên dưới
    support_contact: str = "Điện thoại/Zalo 0865 556 800 hoặc email nguyenhanh7654@gmail.com"
    # Kênh Telegram công khai nhận kết quả mỗi khi có kỳ được công bố (ví dụ @xs247_kq), tùy chọn
    telegram_results_chat_id: str = ""

    # AI (tùy chọn): khóa Claude API và mô hình dùng cho trợ lý, chọn số
    # Nhà cung cấp AI: "anthropic" (Claude) hoặc "openai" (mọi dịch vụ dùng chuẩn API của OpenAI:
    # OpenAI, Google Gemini, DeepSeek, Groq, OpenRouter, Ollama chạy trên máy...)
    ai_provider: str = "anthropic"
    ai_api_key: str = ""
    anthropic_api_key: str = ""          # tên cũ, vẫn dùng được khi ai_provider = anthropic
    ai_model: str = ""
    ai_base_url: str = ""
    ai_requests_per_minute: int = 6

    # Cookie đăng nhập chỉ gửi qua HTTPS. Để trống: bật khi APP_ENV=prod, còn lại theo giao thức của yêu cầu.
    cookie_secure: bool | None = None
    # Giới hạn số lần thử đăng nhập mỗi địa chỉ IP trong 5 phút
    login_attempts_per_ip: int = 10

    user_agent: str = "XS247Bot/0.1 (+https://xs247.mobi/bot)"
    http_timeout_s: float = 15.0

    @field_validator("support_contact", mode="after")
    @classmethod
    def _default_support_contact(cls, v: str) -> str:
        # SUPPORT_CONTACT= (rỗng) trong .env vẫn dùng liên hệ mặc định
        return v.strip() or "Điện thoại/Zalo 0865 556 800 hoặc email nguyenhanh7654@gmail.com"

    @property
    def is_dev(self) -> bool:
        return self.app_env != "prod"

    AI_DEFAULTS: ClassVar[dict] = {"anthropic": ("https://api.anthropic.com", "claude-haiku-5-5"),
                   "openai": ("https://api.openai.com/v1", "gpt-4o-mini")}

    @property
    def ai_key(self) -> str:
        return self.ai_api_key or (self.anthropic_api_key if self.ai_provider == "anthropic" else "")

    @property
    def ai_url(self) -> str:
        return (self.ai_base_url or self.AI_DEFAULTS.get(self.ai_provider, ("", ""))[0]).rstrip("/")

    @property
    def ai_model_name(self) -> str:
        return self.ai_model or self.AI_DEFAULTS.get(self.ai_provider, ("", ""))[1]

    @property
    def ai_enabled(self) -> bool:
        # Ollama chạy trên máy không cần khóa; các dịch vụ khác cần khóa
        local = self.ai_provider == "openai" and any(h in self.ai_base_url for h in ("localhost", "127.0.0.1", "ollama", "host.docker.internal"))
        return bool(self.ai_key) or local

    def min_sources(self, region: str) -> int:
        for part in self.min_sources_by_region.split(","):
            k, _, v = part.strip().partition(":")
            if k == region and v.strip().isdigit():
                return max(1, int(v))
        from .domain.games import GAMES
        if any(g.region == region and g.feed for g in GAMES.values()):
            return 1  # trò chơi Vietlott lấy thẳng từ trang chính thức
        return self.min_matching_sources

    def admin_token_map(self) -> dict[str, tuple[str, str]]:
        out: dict[str, tuple[str, str]] = {}
        for part in filter(None, (p.strip() for p in self.admin_tokens.split(","))):
            bits = part.split(":")
            if len(bits) >= 2 and len(bits[0]) >= 24 and "thay-bang" not in bits[0]:
                out[bits[0]] = (bits[1], bits[2] if len(bits) > 2 else bits[1])
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


@dataclass(frozen=True)
class Window:
    """Khung giờ theo dõi và đối soát của một loại xổ số (giờ Việt Nam)."""

    live_start: time
    live_end: time
    poll_seconds: int
    reconcile: tuple[time, ...]
    warn: time
    critical: time


# Mục 3 tài liệu thiết kế. Giờ quay cần xác nhận lại với nguồn chính thức.
WINDOWS: dict[str, Window] = {
    "mn": Window(time(16, 10), time(16, 50), 5, (time(17, 0), time(19, 0), time(22, 0)), time(17, 0), time(18, 0)),
    "mt": Window(time(17, 10), time(17, 50), 5, (time(18, 0), time(20, 0), time(22, 0)), time(18, 0), time(19, 0)),
    "mb": Window(time(18, 10), time(18, 50), 5, (time(19, 0), time(21, 0), time(23, 0)), time(19, 0), time(20, 0)),
    "vl": Window(time(18, 0), time(19, 0), 30, (time(19, 30), time(21, 0), time(23, 0)), time(19, 30), time(21, 0)),
    "mega": Window(time(18, 0), time(19, 0), 30, (time(19, 30), time(21, 0), time(23, 0)), time(19, 30), time(21, 0)),
}
