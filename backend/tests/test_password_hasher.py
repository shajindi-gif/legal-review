"""Password hasher 单元测试 - Argon2id (新用户) + bcrypt (老用户) 兼容。"""
from __future__ import annotations

import bcrypt

from app.services.auth_service import (
    _HAS_ARGON2,
    hash_password,
    is_legacy_bcrypt,
    needs_rehash,
    opportunistic_rehash,
    verify_password,
)


# ============== Argon2id 优先 (新用户) ==============


def test_hash_password_prefers_argon2id_when_available() -> None:
    h = hash_password("password123")
    if _HAS_ARGON2:
        assert h.startswith("$argon2id$")
    else:
        # 降级到 bcrypt
        assert h.startswith("$2")


def test_verify_argon2_roundtrip() -> None:
    h = hash_password("hello-world-2026")
    assert verify_password("hello-world-2026", h) is True
    assert verify_password("wrong", h) is False


# ============== bcrypt 兼容 (老用户) ==============


def _bcrypt_hash(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=4)).decode("utf-8")


def test_verify_bcrypt_legacy_hash() -> None:
    legacy = _bcrypt_hash("legacy-password-2024")
    assert verify_password("legacy-password-2024", legacy) is True
    assert verify_password("wrong", legacy) is False


def test_is_legacy_bcrypt_detection() -> None:
    assert is_legacy_bcrypt("$2b$12$abcdefghijklmnopqrstuv") is True
    assert is_legacy_bcrypt("$2a$10$abcdef") is True
    assert is_legacy_bcrypt("$argon2id$v=19$m=65536,t=3,p=4$xxx$yyy") is False
    assert is_legacy_bcrypt("") is False


def test_opportunistic_rehash_legacy_bcrypt_returns_new_hash() -> None:
    class FakeUser:
        password_hash = _bcrypt_hash("correct-password-2024")

    new_hash = opportunistic_rehash(FakeUser(), "correct-password-2024")
    assert new_hash is not None
    assert new_hash != FakeUser.password_hash
    # 新 hash 必须是 argon2id (或环境降级时 bcrypt 但和原值不同)
    if _HAS_ARGON2:
        assert new_hash.startswith("$argon2id$")
    assert verify_password("correct-password-2024", new_hash) is True


def test_opportunistic_rehash_already_argon2id_returns_none() -> None:
    if not _HAS_ARGON2:
        return  # 跳过
    h = hash_password("stable-password-2026")
    class FakeUser:
        password_hash = h
    assert opportunistic_rehash(FakeUser(), "stable-password-2026") is None


# ============== needs_rehash ==============


def test_needs_rehash_bcrypt_returns_true() -> None:
    if not _HAS_ARGON2:
        return
    legacy = _bcrypt_hash("x")
    assert needs_rehash(legacy) is True


def test_needs_rehash_fresh_argon2id_returns_false() -> None:
    if not _HAS_ARGON2:
        return
    h = hash_password("fresh-2026")
    assert needs_rehash(h) is False


# ============== 安全边界 ==============


def test_verify_password_empty_hash_returns_false() -> None:
    assert verify_password("anything", "") is False
    assert verify_password("anything", "garbage") is False


def test_verify_password_empty_plain_returns_false() -> None:
    h = hash_password("real-password-2024")
    assert verify_password("", h) is False
