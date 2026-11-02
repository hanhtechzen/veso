"""Nguồn đọc tệp mẫu (backend/fixtures/<draw_id>.json), chỉ dùng khi phát triển và kiểm thử."""
from __future__ import annotations

import json
from pathlib import Path

from .base import Adapter, DrawRef, FetchResult, Parsed, ParseError


class FixtureAdapter(Adapter):
    def _path(self, draw: DrawRef) -> Path:
        base = Path(self.config.get("dir") or self.settings.fixture_dir)
        return base / f"{draw.id}.json"

    async def fetch(self, http, draw: DrawRef) -> FetchResult:
        p = self._path(draw)
        if not p.exists():
            return FetchResult(url=f"file://{p}", status=404, body=b"", content_type="application/json")
        return FetchResult(url=f"file://{p}", status=200, body=p.read_bytes(), content_type="application/json")

    def parse(self, result: FetchResult, draw: DrawRef) -> Parsed:
        try:
            data = json.loads(result.body.decode("utf-8"))
            prizes = data["prizes"]
            if not isinstance(prizes, dict):
                raise TypeError("prizes phải là object")
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError(f"Tệp mẫu sai định dạng: {e}") from e
        return Parsed(prizes={k: [str(x) for x in v] for k, v in prizes.items()}, complete=data.get("complete"))
