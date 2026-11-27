"""Chơi thử: luật dò vé và kiểm tra vé (thuần, không truy cập DB). Không có giá trị tiền thưởng."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from .games import GAMES

PRIZE_NAMES = {
    "db": "Giải Đặc biệt", "g1": "Giải Nhất", "g2": "Giải Nhì", "g3": "Giải Ba", "g4": "Giải Tư",
    "g5": "Giải Năm", "g6": "Giải Sáu", "g7": "Giải Bảy", "g8": "Giải Tám",
    "phu_db": "Giải Phụ đặc biệt", "kk": "Giải Khuyến khích",
    "jackpot": "Jackpot", "jackpot1": "Jackpot 1", "jackpot2": "Jackpot 2",
    "dd": "Độc đắc", "pdb": "Giải phụ Đặc biệt",
}
_ORDER = ["dd", "db", "pdb", "g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8", "phu_db", "kk"]
PICK_GAMES = ("power655", "mega645")
MORE_GAMES = ("lotto535", "max3d", "max3dpro")
LOTTO_SLOTS = ("13:00", "21:00")
_DIGITS3 = re.compile(r"[0-9]{3}")


def check_lotto535(numbers: list, prizes: dict) -> list[str]:
    """Lotto 5/35: vé gồm 5 số chính + số đặc biệt (cuối). Số ĐB của vé chỉ so với số ĐB của kỳ."""
    main = {int(x) for x in prizes.get("main", [])}
    special = {int(x) for x in prizes.get("special", [])}
    vals = [int(x) for x in numbers]
    k = len(set(vals[:5]) & main)
    s = vals[5] in special
    if k == 5:
        return ["dd" if s else "g1"]
    if k in (4, 3):
        return [{(4, True): "g2", (4, False): "g3", (3, True): "g4", (3, False): "g5"}[(k, s)]]
    return ["kk"] if s else []


def check_max3d(number: str, prizes: dict) -> list[str]:
    """Max 3D: trúng mỗi nhóm (db, g1, g2, g3) chứa đúng dãy 3 chữ số đó."""
    return [c for c in ("db", "g1", "g2", "g3") if number in prizes.get(c, [])]


def check_max3dpro(pair: list[str], prizes: dict) -> list[str]:
    """Max 3D Pro: các điều kiện cộng dồn (một vé có thể trúng nhiều giải)."""
    a, b = pair
    db = list(prizes.get("db", []))
    groups = {c: set(prizes.get(c, [])) for c in ("g1", "g2", "g3")}
    all20 = set(db).union(*groups.values())
    hit: list[str] = []
    if len(db) >= 2 and [a, b] == db[:2]:
        hit.append("db")
    elif len(db) >= 2 and a != b and [b, a] == db[:2]:
        hit.append("pdb")
    hit += [c for c in ("g1", "g2", "g3") if a in groups[c] and b in groups[c]]
    if a in all20 and b in all20:
        hit.append("g4")
    if a in db or b in db:
        hit.append("g5")
    if any(x in g for x in (a, b) for g in groups.values()):
        hit.append("g6")
    return hit
XS_DIGITS = {"mb": 5, "mn": 6, "mt": 6}


def check_trad(region: str, number: str, prizes: dict[str, list[str]]) -> list[str]:
    """Dò một vé xổ số truyền thống: trùng các chữ số cuối của số trúng (độ dài theo từng giải).
    Miền Nam/Trung (vé 6 số) có thêm Phụ đặc biệt (sai đúng chữ số đầu so với ĐB) và Khuyến khích
    (đúng chữ số đầu, sai đúng 1 trong 5 chữ số còn lại)."""
    hit: set[str] = set()
    for code, nums in prizes.items():
        for n in nums:
            if n and len(number) >= len(n) and number[-len(n):] == n:
                hit.add(code)
    if region == "mb":
        # Miền Bắc: Khuyến khích = trùng 2 chữ số cuối của giải ĐB (vé đã trúng ĐB/phụ ĐB thì không tính thêm)
        for db in prizes.get("db", []):
            if len(db) >= 2 and len(number) >= 2 and number[-2:] == db[-2:] and number[-len(db):] != db:
                hit.add("kk")
    if region in ("mn", "mt") and len(number) == 6:
        for db in prizes.get("db", []):
            if len(db) != 6 or number == db:
                continue
            if number[1:] == db[1:]:
                hit.add("phu_db")
            elif number[0] == db[0] and sum(a != b for a, b in zip(number[1:], db[1:])) == 1:
                hit.add("kk")
    return sorted(hit, key=lambda c: _ORDER.index(c) if c in _ORDER else len(_ORDER))


def check_pick(game: str, picked: list, prizes: dict) -> str | None:
    """Dò vé chọn số (Power 6/55, Mega 6/45); trả mã hạng hoặc None. Số đặc biệt của Power chỉ phân biệt Jackpot 1/2."""
    main = {int(x) for x in prizes.get("main", [])}
    special = {int(x) for x in prizes.get("special", [])}
    mine = {int(x) for x in picked}
    k = len(mine & main)
    if game == "power655":
        if k == 6:
            return "jackpot1"
        if k == 5:
            return "jackpot2" if mine & special else "g1"
        return {4: "g2", 3: "g3"}.get(k)
    if game == "mega645":
        if k == 6:
            return "jackpot"
        return {5: "g1", 4: "g2", 3: "g3"}.get(k)
    return None


def validate_ticket(game: str, region: str, numbers: list) -> list[str]:
    """Chuẩn hóa số trên vé; ValueError nếu không hợp lệ."""
    if not isinstance(numbers, list):
        raise ValueError("Số không hợp lệ")
    if game == "xs":
        width = XS_DIGITS.get(region)
        if not width:
            raise ValueError("Miền không hợp lệ")
        if len(numbers) != 1 or not isinstance(numbers[0], str) or not re.fullmatch(rf"[0-9]{{{width}}}", numbers[0]):
            raise ValueError(f"Vé miền {'Bắc' if width == 5 else 'Nam, Trung'} gồm đúng 1 dãy {width} chữ số")
        return [numbers[0]]
    if game in PICK_GAMES:
        g = GAMES[game]
        vals = []
        for x in numbers:
            if isinstance(x, bool) or not isinstance(x, (int, str)) or (isinstance(x, str) and not re.fullmatch(r"[0-9]{1,2}", x)):
                raise ValueError("Số không hợp lệ")
            vals.append(int(x))
        if len(vals) != g.main_count or len(set(vals)) != len(vals) or not all(1 <= v <= g.main_max for v in vals):
            raise ValueError(f"{g.name} gồm {g.main_count} số khác nhau từ 01 đến {g.main_max:02d}")
        return [f"{v:02d}" for v in sorted(vals)]
    if game == "lotto535":
        vals = []
        for x in numbers:
            if isinstance(x, bool) or not isinstance(x, (int, str)) or (isinstance(x, str) and not re.fullmatch(r"[0-9]{1,2}", x)):
                raise ValueError("Số không hợp lệ")
            vals.append(int(x))
        main, sp = vals[:5], vals[5:]
        if len(vals) != 6 or len(set(main)) != 5 or not all(1 <= v <= 35 for v in main) or not 1 <= sp[0] <= 12:
            raise ValueError("Lotto 5/35 gồm 5 số khác nhau từ 01 đến 35 và 1 số đặc biệt từ 01 đến 12")
        return [f"{v:02d}" for v in sorted(main)] + [f"{sp[0]:02d}"]
    if game in ("max3d", "max3dpro"):
        n = 1 if game == "max3d" else 2
        if len(numbers) != n or not all(isinstance(x, str) and _DIGITS3.fullmatch(x) for x in numbers):
            raise ValueError("Max 3D gồm 1 dãy 3 chữ số" if n == 1 else "Max 3D Pro gồm 2 dãy 3 chữ số")
        return list(numbers)
    raise ValueError("Trò chơi không hợp lệ")


def closes_at(scheduled_at: datetime, game: str) -> datetime:
    """Giờ ngừng nhận vé: 15 phút trước giờ quay xổ số, 30 phút trước giờ quay Vietlott."""
    return scheduled_at - timedelta(minutes=15 if game == "xs" else 30)


def check_ticket(game: str, region: str, numbers: list[str], prizes: dict) -> list[dict]:
    """Kết quả dò một vé: [{"code","name"}] (rỗng = không trúng)."""
    if game == "xs":
        codes = check_trad(region, numbers[0], prizes)
    elif game == "lotto535":
        codes = check_lotto535(numbers, prizes)
    elif game == "max3d":
        codes = check_max3d(numbers[0], prizes)
    elif game == "max3dpro":
        codes = check_max3dpro(list(numbers), prizes)
    else:
        c = check_pick(game, [int(x) for x in numbers], prizes)
        codes = [c] if c else []
    names = dict(PRIZE_NAMES)
    if game == "xs" and region == "mb":
        # Vé miền Bắc trùng 5 số ĐB: Đặc biệt nếu trùng ký hiệu, khác ký hiệu là Phụ đặc biệt (máy không đọc ký hiệu)
        names["db"] = "Giải Đặc biệt (nếu trùng ký hiệu) hoặc Phụ đặc biệt"
    return [{"code": c, "name": names.get(c, c)} for c in codes]
