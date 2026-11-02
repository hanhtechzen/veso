import pytest

from luckyvision.ai import AiError, RateLimiter, parse_pick, pick_rule


def test_parse_pick_power_validates():
    text = 'Đây: {"sets": [{"numbers": ["3","15","22","31","44","55"], "reason": "ngày sinh"},' \
           '{"numbers": [1,2,3,4,5,56], "reason": "sai"}, {"numbers": [7,7,8,9,10,11], "reason": "trùng"}]}'
    out = parse_pick(text, "power655", 6, 3)
    assert out == [{"numbers": ["03", "15", "22", "31", "44", "55"], "reason": "ngày sinh"}]


def test_parse_pick_xs_size_and_errors():
    out = parse_pick('{"sets":[{"numbers":["08","80","00","99","27"],"reason":"x"}]}', "xs", 5, 1)
    assert out[0]["numbers"] == ["00", "08", "27", "80", "99"]
    with pytest.raises(AiError):
        parse_pick("không có json", "xs", 5, 1)
    with pytest.raises(AiError):
        parse_pick('{"sets":[{"numbers":["1"]}]}', "xs", 5, 1)
    assert "01 đến 55" in pick_rule("power655", 6)


def test_rate_limiter():
    rl = RateLimiter()
    assert all(rl.allow("ip", 3) for _ in range(3))
    assert not rl.allow("ip", 3) and rl.allow("other", 3)
