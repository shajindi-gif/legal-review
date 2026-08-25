"""鉴权相关 Schema - 注册/登录/Token 响应。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """注册请求。"""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    company: str | None = Field(default=None, max_length=128)
    real_name: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    """登录请求。"""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT Token 响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    """刷新 Token 请求。"""

    refresh_token: str


class UserOut(BaseModel):
    """用户信息输出。"""

    id: UUID
    email: str | None = None
    username: str
    real_name: str
    company: str | None = None
    role: str
    plan_tier: str = "free"
    quota_daily: int = 3
    used_today: int = 0
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class QuotaStatus(BaseModel):
    """配额状态。"""

    tier: str
    quota_daily: int
    used_today: int
    remaining: int
    unlimited: bool
    reset_date: str | None = None


# ============== M0: 手机号注册相关 ==============


class SmsSendRequest(BaseModel):
    """发送手机验证码请求 (M0)。

    - phone 接受 13800138000 / +8613800138000 / 0086... 等格式, 后端归一化
    - purpose 限定白名单 (register / login / reset_password / bind_phone / change_phone)
    """

    phone: str = Field(min_length=8, max_length=32)
    purpose: str = Field(default="register")


class SmsSendResponse(BaseModel):
    """发送验证码响应 (M0)。

    生产环境 (APP_ENV=production) 不返回 mock_code, 仅返回 expires_in。
    """

    success: bool = True
    expires_in: int
    mock_code: str | None = None  # 仅 mock + 非生产环境


class PhoneRegisterRequest(BaseModel):
    """手机号注册请求 (M0)。"""

    phone: str = Field(min_length=8, max_length=32)
    code: str = Field(min_length=4, max_length=8)
    password: str = Field(min_length=8, max_length=128)
    real_name: str | None = Field(default=None, max_length=64)
    company: str | None = Field(default=None, max_length=128)


class PhoneRegisterResponse(BaseModel):
    """手机号注册成功响应 (M0)。"""

    user_id: str
    phone: str  # canonical (+8613800138000)
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class PhoneLoginRequest(BaseModel):
    """手机号 + 密码登录请求 (M0)。"""

    phone: str = Field(min_length=8, max_length=32)
    password: str = Field(min_length=8, max_length=128)
