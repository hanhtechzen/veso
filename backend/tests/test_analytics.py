from luckyvision.analytics import device_of, is_bot, normalize_path, page_group, source_of, visitor_id


def test_normalize_path():
    assert normalize_path("/xsmn-26-10-2026?utm=x") == "/xsmn-26-10-2026"
    assert normalize_path("/cong-cu/#may-thoi-gian") == "/cong-cu/#may-thoi-gian"
    assert normalize_path("/cong-cu") == "/cong-cu/"
    assert normalize_path("/xsmb#abc") == "/xsmb"
    assert normalize_path("javascript:alert(1)") is None and normalize_path("/<script>") is None and normalize_path("") is None


def test_groups():
    assert page_group("/") == "Trang chủ"
    assert page_group("/xsmn-26-10-2026") == "XSMN theo ngày" and page_group("/xsmb") == "XSMB mới nhất"
    assert page_group("/vietlott-power-655-29-10-2026") == "Vietlott Power 6/55"
    assert page_group("/vietlott-max-3d-pro") == "Vietlott Max 3D Pro"
    assert page_group("/cong-cu/#mn-thong-ke") == "Công cụ: Miền Nam thống kê"
    assert page_group("/cong-cu/#may-thoi-gian") == "Công cụ: Máy thời gian"
    assert page_group("/xs-tp-hcm") == "Trang từng đài" and page_group("/xs-than-tai-4") == "Xổ số điện toán"


def test_sources_devices_bots():
    assert source_of("", "luckyvision.vn") == "(Vào trực tiếp)"
    assert source_of("https://www.google.com.vn/search?q=xsmn", "luckyvision.vn") == "Google"
    assert source_of("https://luckyvision.vn/xsmb", "luckyvision.vn") is None
    assert source_of("https://m.facebook.com/", "luckyvision.vn") == "Facebook"
    assert device_of("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)") == "Điện thoại" and device_of("Mozilla/5.0 (Windows NT 10.0)") == "Máy tính"
    assert is_bot("Googlebot/2.1") and is_bot("") and not is_bot("Mozilla/5.0 (Windows NT 10.0) Chrome/124")


def test_visitor_id_changes_with_salt():
    a, b = visitor_id("s1", "1.2.3.4", "ua"), visitor_id("s2", "1.2.3.4", "ua")
    assert a != b and len(a) == 16 and "1.2.3.4" not in a
