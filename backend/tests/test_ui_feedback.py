"""Mọi thao tác của người dùng phải có phản hồi rõ ràng (đang xử lý / thành công / lỗi dễ hiểu).
Không có bộ chạy test JS, nên kiểm tra tĩnh nội dung file để các lỗi đã sửa không quay lại."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
TPL = ROOT / "backend" / "xs247" / "site" / "templates"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_shared_helpers_defined():
    s = read(WEB / "assets" / "lv-loading.js")
    for name in ("window.lvToast", "window.lvBusy", "window.lvErr"):
        assert name in s


@pytest.mark.parametrize("page", ["choi-thu.html", "do-ve-anh.html", "live.html", "thong-ke-phan-tich.html",
                                  "admin.html", "cong-cu/index.html"])
def test_static_pages_load_shared_helpers(page):
    assert "/assets/lv-loading.js" in read(WEB / page)


def test_base_template_loads_shared_helpers():
    assert "/assets/lv-loading.js" in read(TPL / "base.html")


def test_free_play_create_and_cancel_give_feedback():
    s = read(WEB / "choi-thu.html")
    assert "lvBusy" in s and "lvToast" in s
    assert re.search(r"lvToast\([^)]*Đã tạo vé", s), "tạo vé phải hiện thông báo nổi"
    assert re.search(r"lvToast\([^)]*Đã hủy vé", s), "hủy vé phải hiện thông báo nổi"


def test_account_actions_no_plaintext_password_prompt_and_errors_caught():
    s = read(WEB / "assets" / "lv-account.js")
    assert not re.search(r"prompt\([^)]*[Mm]ật khẩu", s), "không hỏi mật khẩu bằng prompt() (hiện chữ thường)"
    assert not re.search(r"\.then\(renderAccount\)\s*;", s), "xóa đài/bộ số phải bắt lỗi"
    assert "lvToast" in s


def test_copy_buttons_give_feedback():
    s = read(WEB / "cong-cu" / "index.html")
    body = re.search(r"async function copyText\(.*?\n\}", s, re.S).group(0)
    assert "lvToast" in body, "mọi nút Sao chép phải báo đã sao chép / không sao chép được"


def test_contact_form_blocks_double_submit():
    s = read(TPL / "contact.html")
    assert re.search(r"disabled\s*=\s*true|lvBusy", s)
