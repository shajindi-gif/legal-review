"""手机号规范化工具测试。"""
from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.utils.phone import mask_phone, normalize_phone


# ============== normalize_phone ==============


def test_normalize_china_bare_11_digits() -> None:
    assert normalize_phone("13800138000") == "+8613800138000"


def test_normalize_china_with_plus86() -> None:
    assert normalize_phone("+8613800138000") == "+8613800138000"


def test_normalize_china_with_86_prefix() -> None:
    assert normalize_phone("8613800138000") == "+8613800138000"


def test_normalize_china_with_0086_prefix() -> None:
    assert normalize_phone("008613800138000") == "+8613800138000"


def test_normalize_china_with_spaces_and_dashes() -> None:
    assert normalize_phone("138 0013 8000") == "+8613800138000"
    assert normalize_phone("138-0013-8000") == "+8613800138000"
    assert normalize_phone("+86 138-0013-8000") == "+8613800138000"
    assert normalize_phone("+86 (138) 0013-8000") == "+8613800138000"


@pytest.mark.parametrize("bad", [
    "",
    "123",
    "1380013800",       # 10 位
    "138001380000",     # 12 位
    "23800138000",      # 开头 2 不是 1
    "+86 13800138000ab",
    "not-a-phone",
    "++++++++++",
])
def test_normalize_invalid_raises(bad: str) -> None:
    with pytest.raises(ValidationError):
        normalize_phone(bad)


def test_normalize_international_passthrough() -> None:
    # 美国号码样例
    assert normalize_phone("+14155551234") == "+14155551234"
    # 香港 +852
    assert normalize_phone("+85212345678") == "+85212345678"


# ============== mask_phone ==============


def test_mask_china_phone() -> None:
    assert mask_phone("+8613800138000") == "+86 1380****00"


def test_mask_short_phone() -> None:
    assert mask_phone("+12") == "***"


def test_mask_empty() -> None:
    assert mask_phone("") == "***"
