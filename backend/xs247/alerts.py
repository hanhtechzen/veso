"""Gửi cảnh báo (Telegram, Slack) và nhịp còn sống (healthchecks.io)."""
from __future__ import annotations

import logging

import httpx

from .config import Settings

log = logging.getLogger("xs247.alerts")


async def send(settings: Settings, http: httpx.AsyncClient, text: str, level: str = "warn") -> None:
    prefix = {"info": "ℹ️", "warn": "⚠️", "critical": "🚨"}.get(level, "⚠️")
    message = f"{prefix} XS247: {text}"
    (log.error if level == "critical" else log.warning)(message)
    try:
        if settings.telegram_bot_token and settings.telegram_chat_id:
            await http.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                            json={"chat_id": settings.telegram_chat_id, "text": message}, timeout=10)
        if settings.slack_webhook_url:
            await http.post(settings.slack_webhook_url, json={"text": message}, timeout=10)
    except httpx.HTTPError:
        log.exception("Không gửi được cảnh báo")


async def heartbeat(settings: Settings, http: httpx.AsyncClient) -> None:
    if not settings.healthchecks_url:
        return
    try:
        await http.get(settings.healthchecks_url, timeout=10)
    except httpx.HTTPError:
        log.warning("Không gửi được nhịp còn sống tới healthchecks")
