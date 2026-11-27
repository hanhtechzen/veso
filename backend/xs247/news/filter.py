"""Bộ lọc nội dung: XS247 không đăng nội dung dự đoán/soi cầu/lô đề trong mục Tin tức."""
from __future__ import annotations

import re

_SEP = r"[\s_\-]*"
BANNED = re.compile(
    "|".join([
        rf"d[ựu]{_SEP}b[áa]o",          # dự báo
        rf"d[ựu]{_SEP}[đd]o[áa]n",      # dự đoán, du-doan
        rf"soi{_SEP}c[ầa]u",            # soi cầu
        rf"ch[ốo]t{_SEP}s[ốo]",         # chốt số
        rf"d[àa]n{_SEP}[đd][ềe]",       # dàn đề
        rf"\bl[ôo]{_SEP}[đd][ềe]\b",    # lô đề
        rf"b[ạa]ch{_SEP}th[ủu]",        # bạch thủ
    ]),
    re.IGNORECASE,
)


def is_clean(text: str | None) -> bool:
    return not (text and BANNED.search(text))
