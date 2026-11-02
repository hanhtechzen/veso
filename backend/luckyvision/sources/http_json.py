"""Nguồn trả JSON qua HTTP, dùng cho nhà cung cấp dữ liệu có hợp đồng.

Cấu hình trong data_sources.config, ví dụ:
{
  "url_template": "https://api.provider.example/v1/results?province={province}&date={date}",
  "api_key_env": "PROVIDER_EXAMPLE_API_KEY",      # tên biến môi trường chứa khóa API
  "province_map": {"tp-hcm": "HCM"},             # mã đài của nhà cung cấp, nếu khác
  "prizes_path": "data.prizes",                  # đường dẫn tới object {mã giải: [số...]}
  "prize_map": {"DB": "db", "G1": "g1"},          # đổi mã giải của nhà cung cấp sang mã chuẩn
  "complete_path": "data.complete",              # (tùy chọn) cờ đã đủ giải
  "health_url": "https://api.provider.example/health"
}
"""
from __future__ import annotations

import json
import os

from .base import Adapter, DrawRef, FetchResult, Parsed, ParseError


def _dig(data, path: str | None):
    if not path:
        return data
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


class HttpJsonAdapter(Adapter):
    def _url(self, draw: DrawRef) -> str:
        tpl = self.config.get("url_template")
        if not tpl:
            raise ParseError("Thiếu url_template trong cấu hình nguồn")
        province = (self.config.get("province_map") or {}).get(draw.province, draw.province)
        return tpl.format(province=province, region=draw.region, date=draw.draw_date.isoformat(),
                          seq=draw.draw_seq or "", game=draw.game)

    async def fetch(self, http, draw: DrawRef) -> FetchResult:
        headers = {"Accept": "application/json"}
        key_env = self.config.get("api_key_env")
        if key_env and os.environ.get(key_env):
            headers["Authorization"] = f"Bearer {os.environ[key_env]}"
        url = self._url(draw)
        r = await http.get(url, headers=headers)
        return FetchResult(url=url, status=r.status_code, body=r.content,
                           content_type=r.headers.get("content-type", "application/json"))

    def parse(self, result: FetchResult, draw: DrawRef) -> Parsed:
        try:
            data = json.loads(result.body)
            prizes = _dig(data, self.config.get("prizes_path"))
            complete = None
            if self.config.get("complete_path"):
                complete = bool(_dig(data, self.config["complete_path"]))
        except (ValueError, KeyError) as e:
            raise ParseError(f"Không đọc được dữ liệu nguồn {self.code}: {e}") from e
        if not isinstance(prizes, dict):
            raise ParseError(f"Nguồn {self.code}: prizes không phải object")
        return Parsed(prizes={str(k): [str(x) for x in (v if isinstance(v, list) else [v])] for k, v in prizes.items()},
                      complete=complete)
