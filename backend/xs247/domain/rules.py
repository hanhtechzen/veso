"""Luật chơi và cơ cấu giải (dữ liệu tĩnh, thuần Python) cho trang /luat-choi.

Tổng hợp từ thể lệ của Vietlott và các công ty xổ số kiến thiết; cơ cấu có thể đổi theo đợt phát hành.
"""
from __future__ import annotations

UPDATED = "13/11/2026"

V = "https://www.vietlott.vn/vi/choi/"
SOURCES = [
    ("Power 6/55", V + "power-6-55/gioi-thieu-san-pham-power-655"),
    ("Mega 6/45", V + "mega-6-45/gioi-thieu-san-pham-6-45"),
    ("Lotto 5/35", V + "lotto535/gioi-thieu-san-pham-535"),
    ("Max 3D", V + "max3d/gioi-thieu-san-pham-max3d"),
    ("Max 3D Pro", V + "max3dpro/gioi-thieu-san-pham-max3dpro"),
    ("Keno", V + "keno/gioi-thieu-san-pham-keno"),
    ("Bingo18", V + "bingo/gioi-thieu-san-pham-bingo18"),
    ("Quy định lĩnh thưởng", "https://www.vietlott.vn/vi/trung-thuong/linh-thuong/quy-dinh-linh-thuong"),
]


def money(n: int) -> str:
    """2.000.000.000 -> "2 tỷ", 500.000.000 -> "500 triệu", 40.000 -> "40.000đ"."""
    if n >= 1_000_000_000 and n % 100_000_000 == 0:
        v = n / 1_000_000_000
        return f"{v:g}".replace(".", ",") + " tỷ"
    if n >= 1_000_000 and n % 100_000 == 0:
        v = n / 1_000_000
        return f"{v:g}".replace(".", ",") + " triệu"
    return f"{n:,}".replace(",", ".") + "đ"


def _p(name: str, cond: str, value) -> dict:
    return {"name": name, "cond": cond, "value": value if isinstance(value, str) else money(value)}


XSMB_PRIZES = [
    _p("Đặc biệt", "Trùng 5 chữ số giải Đặc biệt và trùng ký hiệu (mỗi kỳ có 8 ký hiệu trúng giải Đặc biệt)", 500_000_000),
    _p("Phụ đặc biệt", "Trùng 5 chữ số giải Đặc biệt nhưng khác ký hiệu", 25_000_000),
    _p("Nhất", "Trùng 5 chữ số giải Nhất", 10_000_000),
    _p("Nhì (2 giải)", "Trùng 5 chữ số một trong các giải Nhì", 5_000_000),
    _p("Ba (6 giải)", "Trùng 5 chữ số một trong các giải Ba", 1_000_000),
    _p("Tư (4 giải)", "Trùng 4 số cuối một trong các giải Tư", 400_000),
    _p("Năm (6 giải)", "Trùng 4 số cuối một trong các giải Năm", 200_000),
    _p("Sáu (3 giải)", "Trùng 3 số cuối một trong các giải Sáu", 100_000),
    _p("Bảy (4 giải)", "Trùng 2 số cuối một trong các giải Bảy", 40_000),
    _p("Khuyến khích", "Trùng 2 số cuối giải Đặc biệt", 40_000),
]

_SOUTH_PRIZES = [
    _p("Đặc biệt", "Trùng đủ 6 số giải Đặc biệt", 2_000_000_000),
    _p("Phụ Đặc biệt", "Trùng 5 số cuối giải Đặc biệt, chỉ sai chữ số đầu", 50_000_000),
    _p("Khuyến khích", "Trùng chữ số đầu, sai đúng 1 trong 5 chữ số còn lại so với giải Đặc biệt", 6_000_000),
    _p("Nhất", "Trùng 5 số cuối giải Nhất", 30_000_000),
    _p("Nhì", "Trùng 5 số cuối giải Nhì", 15_000_000),
    _p("Ba (2 giải)", "Trùng 5 số cuối một trong các giải Ba", 10_000_000),
    _p("Tư (7 giải)", "Trùng 5 số cuối một trong các giải Tư", 3_000_000),
    _p("Năm", "Trùng 4 số cuối giải Năm", 1_000_000),
    _p("Sáu (3 giải)", "Trùng 4 số cuối một trong các giải Sáu", 400_000),
    _p("Bảy", "Trùng 3 số cuối giải Bảy", 200_000),
    _p("Tám", "Trùng 2 số cuối giải Tám. Ví dụ: vé 123456 trúng giải Tám nếu giải Tám là 56", 100_000),
]

_KT_NOTE = "Vé trùng nhiều giải được lĩnh đủ các giải trúng."
_VL_TOP = "Chỉ lĩnh hạng giải cao nhất trúng."

# Mỗi trò: anchor, name, region (mb/mn/mt/None), price, days, time, top, how, prizes, note, results, play
RULES = [
    {"anchor": "xsmb", "name": "Xổ số miền Bắc", "region": "mb", "price": "10.000đ", "days": "Hằng ngày", "time": "18:15",
     "top": "500 triệu", "how": "Vé có 5 chữ số kèm ký hiệu. Mỗi kỳ quay 27 giải, dò số trên vé với các giải theo số chữ số cuối tương ứng.",
     "prizes": XSMB_PRIZES, "note": "Cơ cấu ký hiệu có thể đổi theo ngày (có ngày 6 giải Đặc biệt). " + _KT_NOTE,
     "results": "/xsmb", "play": True},
    {"anchor": "xsmn", "name": "Xổ số miền Nam", "region": "mn", "price": "10.000đ", "days": "Hằng ngày", "time": "16:15",
     "top": "2 tỷ", "how": "Vé có 6 chữ số, mỗi đài quay 18 lô. Dò số trên vé với từng giải theo số chữ số cuối tương ứng.",
     "prizes": _SOUTH_PRIZES, "note": _KT_NOTE, "results": "/xsmn", "play": True},
    {"anchor": "xsmt", "name": "Xổ số miền Trung", "region": "mt", "price": "10.000đ", "days": "Hằng ngày", "time": "17:15",
     "top": "2 tỷ", "how": "Vé có 6 chữ số, mỗi đài quay 18 lô, cơ cấu giải giống miền Nam.",
     "prizes": _SOUTH_PRIZES, "note": _KT_NOTE, "results": "/xsmt", "play": True},
    {"anchor": "power655", "name": "Power 6/55", "region": None, "price": "10.000đ", "days": "Thứ 3, 5, 7", "time": "18:00",
     "top": "Từ 30 tỷ (tích lũy)", "how": "Chọn 6 số từ 01 đến 55. Mỗi kỳ quay 6 số chính và 1 số đặc biệt (số thứ 7).",
     "prizes": [
         _p("Jackpot 1", "Trùng 6 số", "Từ 30 tỷ (tích lũy)"),
         _p("Jackpot 2", "Trùng 5 số và số đặc biệt (số thứ 7)", "Từ 3 tỷ (tích lũy)"),
         _p("Giải Nhất", "Trùng 5 số", 40_000_000),
         _p("Giải Nhì", "Trùng 4 số", 500_000),
         _p("Giải Ba", "Trùng 3 số", 50_000)],
     "note": _VL_TOP + " Không cần đúng thứ tự. Nhiều người trúng Jackpot thì chia giải.",
     "results": "/vietlott-power-655", "play": True},
    {"anchor": "mega645", "name": "Mega 6/45", "region": None, "price": "10.000đ", "days": "Thứ 4, 6, Chủ nhật", "time": "18:00",
     "top": "Từ 12 tỷ (tích lũy)", "how": "Chọn 6 số từ 01 đến 45. Mỗi kỳ quay 6 số.",
     "prizes": [
         _p("Jackpot", "Trùng 6 số", "Từ 12 tỷ (tích lũy)"),
         _p("Giải Nhất", "Trùng 5 số", 10_000_000),
         _p("Giải Nhì", "Trùng 4 số", 300_000),
         _p("Giải Ba", "Trùng 3 số", 30_000)],
     "note": _VL_TOP + " Không cần đúng thứ tự.", "results": "/vietlott-mega-645", "play": True},
    {"anchor": "lotto535", "name": "Lotto 5/35", "region": None, "price": "10.000đ", "days": "Hằng ngày (2 kỳ mỗi ngày)",
     "time": "13:00 và 21:00", "top": "Từ 6 tỷ (tích lũy)",
     "how": "Chọn 5 số từ 01 đến 35 và 1 số đặc biệt từ 01 đến 12. Bán vé từ 6:00, dừng bán 30 phút trước giờ quay.",
     "prizes": [
         _p("Độc đắc", "Trùng 5 số và số đặc biệt", "Từ 6 tỷ (tích lũy)"),
         _p("Giải Nhất", "Trùng 5 số", 10_000_000),
         _p("Giải Nhì", "Trùng 4 số và số đặc biệt", 5_000_000),
         _p("Giải Ba", "Trùng 4 số", 500_000),
         _p("Giải Tư", "Trùng 3 số và số đặc biệt", 100_000),
         _p("Giải Năm", "Trùng 3 số", 30_000),
         _p("Khuyến khích", "Trùng số đặc biệt (và 0 đến 2 số chính)", 10_000)],
     "note": _VL_TOP + " Khi Độc đắc vượt 12 tỷ mà không ai trúng, kỳ cuối của ngày kế tiếp là kỳ chia giải Độc đắc cho các giải Nhất đến Năm.",
     "results": "/vietlott-lotto-535", "play": True},
    {"anchor": "max3d", "name": "Max 3D", "region": None, "price": "10.000đ", "days": "Thứ 2, 4, 6", "time": "18:00",
     "top": "1 triệu", "how": "Chọn 1 bộ 3 chữ số từ 000 đến 999. Mỗi kỳ quay 20 bộ số. Ngoài ra còn Max 3D+ và chơi tổ hợp, xem thêm tại vietlott.vn.",
     "prizes": [
         _p("Đặc biệt", "Trùng 1 trong 2 bộ số giải Đặc biệt", 1_000_000),
         _p("Giải Nhất", "Trùng 1 trong 4 bộ số giải Nhất", 350_000),
         _p("Giải Nhì", "Trùng 1 trong 6 bộ số giải Nhì", 210_000),
         _p("Giải Ba", "Trùng 1 trong 8 bộ số giải Ba", 100_000)],
     "note": "Trúng nhiều giải được lĩnh tổng các giải trúng.", "results": "/vietlott-max-3d", "play": True},
    {"anchor": "max3dpro", "name": "Max 3D Pro", "region": None, "price": "10.000đ", "days": "Thứ 3, 5, 7", "time": "18:00",
     "top": "2 tỷ", "how": "Chọn 2 bộ 3 chữ số. Mỗi kỳ quay 20 bộ số.",
     "prizes": [
         _p("Đặc biệt", "Trùng 2 bộ số giải Đặc biệt đúng thứ tự", 2_000_000_000),
         _p("Phụ Đặc biệt", "Trùng 2 bộ số giải Đặc biệt ngược thứ tự", 400_000_000),
         _p("Giải Nhất", "Trùng 2 trong 4 bộ số giải Nhất", 30_000_000),
         _p("Giải Nhì", "Trùng 2 trong 6 bộ số giải Nhì", 10_000_000),
         _p("Giải Ba", "Trùng 2 trong 8 bộ số giải Ba", 4_000_000),
         _p("Giải Tư", "Trùng 2 bộ bất kỳ trong 20 bộ số", 1_000_000),
         _p("Giải Năm", "Trùng 1 bộ số giải Đặc biệt", 100_000),
         _p("Giải Sáu", "Trùng 1 bộ số giải Nhất, Nhì hoặc Ba", 40_000)],
     "note": "Được lĩnh tổng các giải trúng.", "results": "/vietlott-max-3d-pro", "play": True},
    {"anchor": "keno", "name": "Keno", "region": None, "price": "10.000đ", "days": "Hằng ngày",
     "time": "8 phút một kỳ, từ 6:00 đến khoảng 21:52", "top": "2 tỷ",
     "how": "Chọn từ 1 đến 10 số trong 01 đến 80. Mỗi kỳ quay 20 số. Giải tùy số đã chọn và số trùng; có thêm cách chơi Lớn/Nhỏ, Chẵn/Lẻ.",
     "prizes": [
         _p("Cao nhất", "Chọn 10 số, trùng cả 10 số", 2_000_000_000),
         _p("Các giải khác", "Tùy số đã chọn (1 đến 10) và số trùng; xem bảng giải của Vietlott", "Theo bảng giải")],
     "note": "Giá trị giải phụ thuộc cách chơi; hãy đối chiếu bảng giải trên vietlott.vn.",
     "results": "/vietlott-keno", "play": False},
    {"anchor": "bingo18", "name": "Bingo18", "region": None, "price": "10.000đ", "days": "Hằng ngày",
     "time": "6 phút một kỳ, từ 6:00 đến khoảng 21:53", "top": "1,2 triệu",
     "how": "Mỗi kỳ quay 3 số từ 1 đến 6. Có thể cược 1 số, 2 số trùng, 3 số trùng, tổng 3 đến 18, hoặc Lớn (12 đến 18) / Hòa (10 đến 11) / Nhỏ (3 đến 9).",
     "prizes": [
         _p("Cao nhất", "Cược đúng bộ 3 số trùng nhau (vé 10.000đ)", 1_200_000),
         _p("Các cách chơi khác", "Tùy loại cược: 1 số, 2 số trùng, tổng, Lớn/Hòa/Nhỏ", "Theo bảng giải")],
     "note": "Giá trị giải phụ thuộc cách chơi; hãy đối chiếu bảng giải trên vietlott.vn.",
     "results": "/vietlott-bingo18", "play": False},
]

# Phần "Lĩnh thưởng & thuế"
CLAIM = {
    "vietlott": ["Hạn lĩnh thưởng Vietlott: 60 ngày kể từ ngày quay thưởng; nhận thưởng sau ít nhất 60 phút kể từ khi công bố kết quả.",
                 "Giải từ 10 tỷ trở xuống lĩnh tại đại lý; giải lớn hơn lĩnh tại chi nhánh hoặc trụ sở Vietlott."],
    "kien_thiet": "Xổ số kiến thiết: thường trong 30 ngày kể từ ngày quay, xem hạn ghi ở mặt sau vé.",
    "tax": "Thuế thu nhập cá nhân 10% trên phần giá trị vượt 20 triệu đồng mỗi lần trúng (từ 01/07/2026; trước đó ngưỡng là 10 triệu đồng).",
    "tax_example": "Ví dụ: trúng 50 triệu đồng, phần vượt là 30 triệu, thuế 3 triệu đồng, thực nhận 47 triệu đồng.",
}

FOOTER = (f"Thông tin tổng hợp từ thể lệ của Vietlott và các công ty xổ số, cập nhật {UPDATED}. "
          "Cơ cấu giải có thể thay đổi theo từng đợt phát hành; hãy đối chiếu thể lệ in trên vé.")

# Thứ tự chip nhảy nhanh
CHIP_LABELS = {"xsmb": "Miền Bắc", "xsmn": "Miền Nam", "xsmt": "Miền Trung", "power655": "Power 6/55", "mega645": "Mega 6/45",
               "lotto535": "Lotto 5/35", "max3d": "Max 3D", "max3dpro": "Max 3D Pro", "keno": "Keno", "bingo18": "Bingo18"}
