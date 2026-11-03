"""Các trò chơi ngoài xổ số kiến thiết truyền thống: luật chung để kiểm tra, hiển thị, thống kê.

Ba kiểu luật:
  pick   chọn các số khác nhau trong một khoảng (Power 6/55, Mega 6/45, Lotto 5/35, Keno, 6x36)
  digits các dãy chữ số có độ dài cố định (Max 3D, Max 3D Pro, Thần Tài 4, 1*2*3)
  dice   các số từ 1 đến 6, được phép trùng (Bingo18)

Trò chơi quay nhiều kỳ mỗi ngày (multi_daily) dùng mã kỳ có thêm số kỳ: keno-keno-2026-11-03-0301574.
Trò chơi lấy theo "dòng kết quả mới nhất" (feed) không cần lập lịch trước; worker định kỳ đọc trang kết quả.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import comb


@dataclass(frozen=True)
class Game:
    code: str
    region: str
    name: str
    kind: str = "pick"            # pick | digits | dice
    main_count: int = 0           # pick: số lượng số được quay; dice: số viên xúc xắc
    main_max: int = 0             # pick: số lớn nhất (nhỏ nhất là 1)
    special_max: int = 0          # >0: có số đặc biệt; Power dùng chung lồng cầu (special_same_drum)
    special_same_drum: bool = False
    slug: str = ""
    family: str = "vietlott"      # vietlott | dientoan
    multi_daily: bool = False
    feed: bool = False
    forecastable: bool = False    # có chạy mô hình dự báo, xác suất từng số
    prizes: tuple = field(default_factory=tuple)  # digits: ((mã, tên, số lượng, số chữ số), ...)
    schedule: str = ""
    seq_width: int = 5

    @property
    def jackpot_odds(self) -> int:
        if self.kind != "pick" or not self.main_count:
            return 0
        n = comb(self.main_max, self.main_count)
        return n * self.special_max if self.special_max and not self.special_same_drum else n


MAX3D_PRIZES = (("db", "Giải Đặc biệt", 2, 3), ("g1", "Giải Nhất", 4, 3), ("g2", "Giải Nhì", 6, 3), ("g3", "Giải Ba", 8, 3))

GAMES: dict[str, Game] = {g.code: g for g in [
    Game("power655", "vl", "Vietlott Power 6/55", "pick", 6, 55, 55, True, "vietlott-power-655",
         forecastable=True, schedule="Thứ Ba, Năm, Bảy lúc 18:00"),
    Game("mega645", "mega", "Vietlott Mega 6/45", "pick", 6, 45, slug="vietlott-mega-645",
         forecastable=True, schedule="Thứ Tư, Sáu, Chủ nhật lúc 18:00"),
    Game("lotto535", "lotto", "Vietlott Lotto 5/35", "pick", 5, 35, 12, False, "vietlott-lotto-535",
         multi_daily=True, feed=True, forecastable=True, schedule="2 kỳ mỗi ngày"),
    Game("keno", "keno", "Vietlott Keno", "pick", 20, 80, slug="vietlott-keno", multi_daily=True, feed=True,
         schedule="Khoảng 10 phút một kỳ, từ 6:00 đến 22:00 hằng ngày", seq_width=7),
    Game("max3d", "max3d", "Vietlott Max 3D", "digits", slug="vietlott-max-3d", feed=True, prizes=MAX3D_PRIZES,
         schedule="Thứ Hai, Tư, Sáu lúc 18:00"),
    Game("max3dpro", "max3dpro", "Vietlott Max 3D Pro", "digits", slug="vietlott-max-3d-pro", feed=True, prizes=MAX3D_PRIZES,
         schedule="Thứ Ba, Năm, Bảy lúc 18:00"),
    Game("bingo18", "bingo", "Vietlott Bingo18", "dice", 3, slug="vietlott-bingo18", multi_daily=True, feed=True,
         schedule="Nhiều kỳ mỗi ngày", seq_width=7),
    Game("dt123", "dt123", "Xổ số điện toán 1*2*3", "digits", slug="xs-dien-toan-123", family="dientoan",
         prizes=(("g1", "Số 1 chữ số", 1, 1), ("g2", "Số 2 chữ số", 1, 2), ("g3", "Số 3 chữ số", 1, 3))),
    Game("tt4", "tt4", "Xổ số Thần Tài 4", "digits", slug="xs-than-tai-4", family="dientoan",
         prizes=(("db", "Số trúng thưởng", 1, 4),)),
    Game("dt6x36", "dt6x36", "Xổ số điện toán 6x36", "pick", 6, 36, slug="xs-dien-toan-6x36", family="dientoan",
         forecastable=True),
]}
REGION_GAME = {g.region: g.code for g in GAMES.values()}
REGION_PROVINCE = {"mb": "mb", **{g.region: g.code for g in GAMES.values()}}
GAME_REGIONS = set(REGION_GAME)
ALL_REGIONS = {"mb", "mn", "mt"} | GAME_REGIONS


def game_of_region(region: str) -> str:
    return REGION_GAME.get(region, "xs")


def is_pick(game: str) -> bool:
    return game in GAMES and GAMES[game].kind == "pick"
