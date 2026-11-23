"""Thống kê truy cập: chuẩn hóa đường dẫn, nhận diện thiết bị, lọc bot, nhóm trang để phân tích."""
from __future__ import annotations

import hashlib
import re
import secrets
from urllib.parse import urlsplit

PATH_RE = re.compile(r"^/[a-z0-9\-._/]{0,150}(#[a-z0-9\-]{1,40})?$")
BOT_RE = re.compile(r"bot|crawl|spider|slurp|headless|lighthouse|preview|facebookexternalhit|curl|wget|python|httpx|go-http|java/", re.I)
SEARCH = {"google.": "Google", "bing.com": "Bing", "coccoc.com": "Cốc Cốc", "duckduckgo.com": "DuckDuckGo", "yahoo.": "Yahoo"}
SOCIAL = {"facebook.com": "Facebook", "fb.com": "Facebook", "zalo.me": "Zalo", "t.me": "Telegram", "telegram.": "Telegram",
          "tiktok.com": "TikTok", "youtube.com": "YouTube", "x.com": "X", "twitter.com": "X", "reddit.com": "Reddit"}


def normalize_path(p: str) -> str | None:
    """Giữ đường dẫn trang (bỏ tham số); chỉ trang Công cụ giữ phần #mục. Đường dẫn lạ bị bỏ qua."""
    if not p or not isinstance(p, str):
        return None
    p = p.strip().lower()
    path, _, frag = p.partition("#")
    path = path.split("?", 1)[0] or "/"
    if path.startswith("/cong-cu") and frag:
        frag = re.sub(r"[^a-z0-9\-].*$", "", frag)
        path = "/cong-cu/#" + frag if frag else "/cong-cu/"
    elif path == "/cong-cu":
        path = "/cong-cu/"
    return path if PATH_RE.match(path) else None


def is_bot(ua: str) -> bool:
    return not ua or bool(BOT_RE.search(ua))


def device_of(ua: str) -> str:
    u = ua or ""
    if re.search(r"iPad|Tablet", u, re.I):
        return "Máy tính bảng"
    if re.search(r"Mobi|Android|iPhone", u, re.I):
        return "Điện thoại"
    return "Máy tính"


def source_of(referrer: str, own_host: str) -> str | None:
    """Nguồn khách đến; None nếu chuyển trang trong chính trang web."""
    if not referrer:
        return "(Vào trực tiếp)"
    try:
        host = (urlsplit(referrer).hostname or "").lower()
    except ValueError:
        return "(Khác)"
    if not host:
        return "(Vào trực tiếp)"
    if host == own_host or host.endswith("." + own_host):
        return None
    host = host[4:] if host.startswith("www.") else host
    for k, name in {**SEARCH, **SOCIAL}.items():
        if k in host:
            return name
    return host[:60]


def visitor_id(salt: str, ip: str, ua: str) -> str:
    return hashlib.sha256(f"{salt}|{ip}|{ua}".encode()).hexdigest()[:16]


def new_salt() -> str:
    return secrets.token_hex(16)


TOOL_NAMES = {"kq": "Kết quả hôm nay", "trang-chu": "Power: trang chủ", "ket-qua": "Power: kết quả", "thong-ke": "Power: thống kê",
              "dau-truong": "Đấu trường", "may-thoi-gian": "Máy thời gian", "tao-so": "Tạo bộ số", "so-du-doan": "Sổ dự đoán",
              "do-ve": "Dò vé", "quan-tri": "Quản trị"}
VIEW_NAMES = {"tong-quan": "tổng quan", "ket-qua": "kết quả", "thong-ke": "thống kê", "du-bao": "dự báo", "danh-gia": "đánh giá"}
RG = {"mb": "Miền Bắc", "mn": "Miền Nam", "mt": "Miền Trung"}


def page_group(path: str) -> str:
    """Nhóm trang để phân tích (ví dụ mọi trang /xsmn-dd-mm-yyyy là 'XSMN theo ngày')."""
    if path == "/":
        return "Trang chủ"
    m = re.match(r"^/xs(mb|mn|mt)(-\d{2}-\d{2}-\d{4})?$", path)
    if m:
        return f"XS{m[1].upper()} " + ("theo ngày" if m[2] else "mới nhất")
    if path.startswith("/cong-cu/"):
        h = path.split("#", 1)[1] if "#" in path else "kq"
        m = re.match(r"^(mb|mn|mt)-(.+)$", h)
        if m:
            return f"Công cụ: {RG[m[1]]} {VIEW_NAMES.get(m[2], m[2])}"
        return "Công cụ: " + TOOL_NAMES.get(h, h)
    if path == "/tin-tuc" or path.startswith("/tin-tuc/"):
        return "Tin tức"
    if path.startswith("/so-ket-qua"):
        return "Sổ kết quả"
    if path.startswith("/thong-ke"):
        return "Thống kê"
    if path.startswith("/xs-dien-toan") or path.startswith("/xs-than-tai"):
        return "Xổ số điện toán"
    if path.startswith("/vietlott"):
        m = re.match(r"^/vietlott-([a-z0-9-]+?)(-\d{2}-\d{2}-\d{4})?$", path)
        return "Vietlott " + (m[1].replace("-", " ").replace("power 655", "Power 6/55").replace("mega 645", "Mega 6/45")
                               .replace("lotto 535", "Lotto 5/35").replace("max 3d", "Max 3D").replace("keno", "Keno")
                               .replace("bingo18", "Bingo18").replace(" pro", " Pro") if m else "(tổng hợp)")
    if path.startswith("/xs-"):
        return "Trang từng đài"
    return {"/live.html": "Tường thuật trực tiếp", "/thong-ke-phan-tich.html": "Thống kê phân tích", "/du-doan.html": "Dự báo và AI"}.get(path, "Khác")
