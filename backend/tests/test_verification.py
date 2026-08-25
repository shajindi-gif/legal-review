"""验证码服务单元测试 (纯逻辑, 不依赖 DB)。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import CodeError, RateLimitedError, ValidationError
from app.services.sms import SMSResult
from app.services.verification import (
    CODE_LENGTH,
    CODE_TTL_SECONDS,
    MAX_VERIFY_ATTEMPTS,
    PER_PHONE_COOLDOWN_SECONDS,
    VALID_PURPOSES,
    VerificationService,
)


def _make_session_mock() -> MagicMock:
    session = MagicMock()
    session.scalar = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


def _make_sms_mock() -> MagicMock:
    sms = MagicMock()
    sms.send_code = AsyncMock(
        return_value=SMSResult(
            success=True,
            provider="mock",
            message_id="mock-123",
            mock_code="123456",
        )
    )
    return sms


# ============== 验证码生成 ==============


def test_generate_code_is_6_digits() -> None:
    for _ in range(20):
        code = VerificationService._generate_code()
        assert len(code) == CODE_LENGTH
        assert code.isdigit()


def test_hash_and_verify_code_roundtrip() -> None:
    h = VerificationService._hash_code("123456")
    assert h != "123456"
    assert VerificationService._verify_code_hash("123456", h) is True
    assert VerificationService._verify_code_hash("000000", h) is False


# ============== send_code 限流 ==============


@pytest.mark.asyncio
async def test_send_code_rejects_unsupported_channel() -> None:
    svc = VerificationService(_make_session_mock(), sms=_make_sms_mock())
    with pytest.raises(ValidationError, match="不支持的 channel"):
        await svc.send_code(target="+8613800138000", channel="push", purpose="register")


@pytest.mark.asyncio
async def test_send_code_rejects_unsupported_purpose() -> None:
    svc = VerificationService(_make_session_mock(), sms=_make_sms_mock())
    with pytest.raises(ValidationError, match="不支持的 purpose"):
        await svc.send_code(target="+8613800138000", purpose="random_purpose")


@pytest.mark.asyncio
async def test_send_code_cooldown_blocks_second_request() -> None:
    """60s 冷却: 第一次返回 None (无历史), 第二次返回刚发出的 row → 触发冷却。"""
    session = _make_session_mock()
    sms = _make_sms_mock()
    # send_code (无 ip_address) 调 scalar 2 次: cooldown + day_count
    # 第一次 send_code: cooldown=None, day_count=0  (返回 success)
    # 第二次 send_code: cooldown=recent_row → raise
    recent_row = MagicMock()
    recent_row.created_at = __import__("datetime").datetime.utcnow()
    session.scalar.side_effect = [None, 0, recent_row]

    svc = VerificationService(session, sms=sms)
    # 第一次: 应该成功
    r1 = await svc.send_code(target="+8613800138000", purpose="register")
    assert r1.expires_in == CODE_TTL_SECONDS
    assert r1.mock_code == "123456"
    sms.send_code.assert_awaited()

    # 第二次: 触发 60s 冷却
    with pytest.raises(CodeError) as ei:
        await svc.send_code(target="+8613800138000", purpose="register")
    assert ei.value.code == "rate_limited"


@pytest.mark.asyncio
async def test_send_code_ip_rate_limit_blocks() -> None:
    session = _make_session_mock()
    sms = _make_sms_mock()
    # 第一次: cooldown None, ip 计数 0
    # 第二次调用: cooldown None, ip 计数 5 (>= max)
    session.scalar.side_effect = [None, 0, 0, None, 5]
    svc = VerificationService(session, sms=sms)
    await svc.send_code(target="+8613800138001", purpose="register", ip_address="1.2.3.4")
    with pytest.raises(RateLimitedError):
        await svc.send_code(target="+8613800138002", purpose="register", ip_address="1.2.3.4")


@pytest.mark.asyncio
async def test_send_code_daily_limit_blocks() -> None:
    session = _make_session_mock()
    sms = _make_sms_mock()
    # cooldown None, day_count 10 (>= max) — 第二次 scalar 调 day_count
    session.scalar.side_effect = [None, 10]
    svc = VerificationService(session, sms=sms)
    with pytest.raises(CodeError) as ei:
        await svc.send_code(target="+8613800138003", purpose="register")
    assert ei.value.code == "rate_limited"


@pytest.mark.asyncio
async def test_send_code_email_not_implemented() -> None:
    session = _make_session_mock()
    # 让 send_code 顺利走到 "email 暂未实现" 校验, 不要被 cooldown 拦截
    session.scalar.side_effect = [None, 0]
    svc = VerificationService(session, sms=_make_sms_mock())
    with pytest.raises(CodeError) as ei:
        await svc.send_code(target="a@b.com", channel="email", purpose="register")
    assert ei.value.code == "email_not_implemented"


# ============== verify 校验 ==============


@pytest.mark.asyncio
async def test_verify_no_record_raises() -> None:
    session = _make_session_mock()
    session.scalar.return_value = None
    svc = VerificationService(session, sms=_make_sms_mock())
    with pytest.raises(CodeError) as ei:
        await svc.verify(target="+8613800138000", code="000000", purpose="register")
    assert ei.value.code == "invalid_code"


@pytest.mark.asyncio
async def test_verify_expired_raises_and_marks_used() -> None:
    from datetime import datetime, timedelta
    session = _make_session_mock()
    row = MagicMock()
    row.code_hash = VerificationService._hash_code("123456")
    row.attempt_count = 0
    row.max_attempts = MAX_VERIFY_ATTEMPTS
    row.expires_at = datetime.utcnow() - timedelta(seconds=10)
    row.used_at = None
    session.scalar.return_value = row
    svc = VerificationService(session, sms=_make_sms_mock())
    with pytest.raises(CodeError) as ei:
        await svc.verify(target="+8613800138000", code="123456", purpose="register")
    assert ei.value.code == "code_expired"
    assert row.used_at is not None  # 过期立即作废


@pytest.mark.asyncio
async def test_verify_too_many_attempts_locks() -> None:
    from datetime import datetime, timedelta
    session = _make_session_mock()
    row = MagicMock()
    row.code_hash = VerificationService._hash_code("123456")
    row.attempt_count = MAX_VERIFY_ATTEMPTS
    row.max_attempts = MAX_VERIFY_ATTEMPTS
    row.expires_at = datetime.utcnow() + timedelta(seconds=300)
    row.used_at = None
    session.scalar.return_value = row
    svc = VerificationService(session, sms=_make_sms_mock())
    with pytest.raises(CodeError) as ei:
        await svc.verify(target="+8613800138000", code="123456", purpose="register")
    assert ei.value.code == "code_locked"
    assert row.used_at is not None


@pytest.mark.asyncio
async def test_verify_wrong_code_increments_attempt() -> None:
    from datetime import datetime, timedelta
    session = _make_session_mock()
    row = MagicMock()
    row.code_hash = VerificationService._hash_code("123456")
    row.attempt_count = 0
    row.max_attempts = MAX_VERIFY_ATTEMPTS
    row.expires_at = datetime.utcnow() + timedelta(seconds=300)
    row.used_at = None
    session.scalar.return_value = row
    svc = VerificationService(session, sms=_make_sms_mock())
    with pytest.raises(CodeError) as ei:
        await svc.verify(target="+8613800138000", code="000000", purpose="register")
    assert ei.value.code == "invalid_code"
    assert row.attempt_count == 1


@pytest.mark.asyncio
async def test_verify_success_marks_used() -> None:
    from datetime import datetime, timedelta
    session = _make_session_mock()
    row = MagicMock()
    row.code_hash = VerificationService._hash_code("123456")
    row.attempt_count = 0
    row.max_attempts = MAX_VERIFY_ATTEMPTS
    row.expires_at = datetime.utcnow() + timedelta(seconds=300)
    row.used_at = None
    session.scalar.return_value = row
    svc = VerificationService(session, sms=_make_sms_mock())
    assert await svc.verify(target="+8613800138000", code="123456", purpose="register") is True
    assert row.used_at is not None  # 一次性使用


# ============== 常量校验 ==============


def test_purpose_whitelist_contains_register() -> None:
    assert "register" in VALID_PURPOSES


def test_constants_are_correct() -> None:
    assert CODE_TTL_SECONDS == 300
    assert PER_PHONE_COOLDOWN_SECONDS == 60
    assert MAX_VERIFY_ATTEMPTS == 5
