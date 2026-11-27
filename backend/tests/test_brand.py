"""Thương hiệu XS247: không còn chữ "LuckyVision" hay "SoxoLive" hiển thị cho người dùng; liên hệ có ở chân trang."""
from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI

from xs247.config import Settings
from xs247.site import routes

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = Path(routes.__file__).parent / "templates"
OLD_BRANDS = ("LuckyVision", "SoxoLive", "soxolive")


def _user_visible_files() -> list[Path]:
    files = list(TEMPLATES.glob("*.html"))
    files += (ROOT / "web").glob("*.html")
    files.append(ROOT / "web" / "cong-cu" / "index.html")
    files.append(ROOT / "web" / "manifest.webmanifest")
    return files


def test_no_old_brand_in_user_visible_files():
    files = _user_visible_files()
    assert len(files) > 10
    bad = [f.name for f in files if any(old in f.read_text(encoding="utf-8") for old in OLD_BRANDS)]
    assert not bad, bad


def test_no_old_brand_in_route_strings_and_nav_js():
    src = Path(routes.__file__).read_text(encoding="utf-8")
    assert not any(old in src for old in OLD_BRANDS)
    assert 'class="brand-live"' in routes.NAV_JS and "XS247" in routes.NAV_JS


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.site_name == "XS247"
    assert s.contact_phone == "0865 556 800"
    assert s.contact_email == "nguyenhanh7654@gmail.com"
    assert "0865 556 800" in s.support_contact
    assert s.user_agent.startswith("XS247Bot/")
    assert Settings(_env_file=None, support_contact="").support_contact == s.support_contact


class _Cur:
    async def fetchall(self):
        return []

    async def fetchone(self):
        return None


class _DB:
    async def execute(self, sql, params=None):
        return _Cur()


class _Pool:
    def connection(self):
        class CM:
            async def __aenter__(self_):
                return _DB()

            async def __aexit__(self_, *a):
                return False

        return CM()


async def test_footer_and_header_show_brand_and_phone():
    app = FastAPI()
    app.include_router(routes.router)
    app.state.pool = _Pool()
    app.state.settings = Settings(_env_file=None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/luat-choi")
        contact = await c.get("/lien-he")
    assert r.status_code == 200, r.text[:300]
    html = r.text
    assert 'href="tel:0865556800"' in html and "0865 556 800" in html
    assert "mailto:nguyenhanh7654@gmail.com" in html
    assert 'class="brand-live"' in html and "XS247" in html
    assert 'href="/favicon.svg"' in html and 'property="og:site_name" content="XS247"' in html
    assert contact.status_code == 200
    assert 'class="contact-direct"' in contact.text and "tel:0865556800" in contact.text
