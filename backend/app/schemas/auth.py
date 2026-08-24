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
