import base64
import hashlib
import hmac
import struct

from xs247.auth import (hash_password, new_session_token, password_problem, token_hash, totp_code, totp_uri,
                              verify_password, verify_totp)


def test_password_hash_roundtrip_and_salt():
    h1, h2 = hash_password("Matkhau123"), hash_password("Matkhau123")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert verify_password("Matkhau123", h1)
    assert not verify_password("matkhau123", h1)
    assert not verify_password("x", "hỏng")


def test_password_rules():
    assert password_problem("ngan1A")
    assert password_problem("khongcohoa123")
    assert password_problem("KhongCoSo")
    assert password_problem("DuManh2026x") is None


def test_totp_rfc6238_vector():
    # Vector chuẩn RFC 6238 (SHA1), khóa "12345678901234567890", thời điểm 59 -> 94287082 (8 chữ số)
    secret = base64.b32encode(b"12345678901234567890").decode()
    key = b"12345678901234567890"
    d = hmac.new(key, struct.pack(">Q", 59 // 30), hashlib.sha1).digest()
    o = d[-1] & 0xF
    full = (struct.unpack(">I", d[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 8
    assert str(full).zfill(8) == "94287082"
    assert totp_code(secret, 59) == "287082"


def test_totp_verify_window():
    secret = base64.b32encode(b"abcdefghij0123456789").decode().rstrip("=")
    assert verify_totp(secret, totp_code(secret))
    assert not verify_totp(secret, "000000") or totp_code(secret) == "000000"
    assert not verify_totp(secret, "12345")
    assert totp_uri(secret, "an").startswith("otpauth://totp/XS247:an?secret=")


def test_session_token_hash():
    t, h = new_session_token()
    assert len(t) > 30 and token_hash(t) == h and h != t


def test_totp_replay_rejected():
    secret = base64.b32encode(b"abcdefghij0123456789").decode().rstrip("=")
    step = verify_totp(secret, totp_code(secret))
    assert step
    assert verify_totp(secret, totp_code(secret), after_step=step) is None
