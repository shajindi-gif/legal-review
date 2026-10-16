"""鉴权相关 Schema - 注册/登录/Token 响应。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
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
    """刷新 Token 请求（refresh_token 可空：优先读 HttpOnly Cookie）。"""

    refresh_token: str | None = None


class UserOut(BaseModel):
    """用户信息输出。

    tenant_id：Strangler 双跑后由 Core /auth/me 返回（模板 §3.3 新增字段）。
    """

    id: UUID
    email: str | None = None
    username: str
    real_name: str
    company: str | None = None
    role: str
    plan_tier: str = "free"
    quota_daily: int = 2
    used_today: int = 0
    remaining: int = 2
    last_login_at: datetime | None = None
    tenant_id: UUID | None = None

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
    - purpose 限定白名单 (login / register / reset_password / bind_phone / change_phone)
    """

    phone: str = Field(min_length=8, max_length=32)
    purpose: str = Field(default="login")


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


# ============== 统一账号：邮箱验证码 / 验证码登录 / 登录方式 / 会话 ==============


class EmailSendRequest(BaseModel):
    """发送邮箱验证码请求。

    - email 由 EmailStr 校验，后端仅 strip + 小写规范化（不做别名折叠）
    - purpose 限定白名单 (login / register / reset_password / bind_email / change_email)
    """

    email: EmailStr
    purpose: str = Field(default="login")


class EmailSendResponse(BaseModel):
    """发送邮箱验证码响应。

    生产环境 (environment=prod) 不返回 mock_code。
    """

    success: bool = True
    expires_in: int
    mock_code: str | None = None


class VerificationLoginRequest(BaseModel):
    """验证码统一登录/注册请求 (手机号或邮箱)。

    - channel: phone | email
    - target: 手机号（任意格式，后端归一化）或邮箱
    - code: 6 位验证码
    """

    channel: Literal["phone", "email"]
    target: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=4, max_length=8)


class VerificationLoginResponse(BaseModel):
    """验证码登录/注册成功响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    is_new_user: bool = False
    user: UserOut


class LoginMethod(BaseModel):
    """单一登录方式的开关状态。"""

    key: str          # phone / email / password / wechat / qq / weibo / xiaohongshu
    enabled: bool
    label: str


class LoginMethodsResponse(BaseModel):
    """登录入口可选方式列表（未开通渠道 enabled=False，前台不展示）。"""

    methods: list[LoginMethod]


class LogoutRequest(BaseModel):
    """登出请求：撤销当前会话的 refresh token（body 可空，优先读 HttpOnly Cookie）。"""

    refresh_token: str | None = None


# ============== 统一账号升级（P0）：本地密码注册/登录 + 密码管理 + 绑定 + 会话 ==============


class PasswordRegisterRequest(BaseModel):
    """本地邮箱密码注册请求。

    - 邮箱格式由 EmailStr 校验
    - 密码遵循 NIST：长度 8-128，不强制组合规则（系统有验证码+登录限流兜底）
    - agreed_terms 必须为 true（个保法合规，前端有勾选框）
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    real_name: str | None = Field(default=None, max_length=64)
    company: str | None = Field(default=None, max_length=128)
    agreed_terms: bool = Field(default=True)


class PasswordLoginRequest(BaseModel):
    """本地密码登录请求（identifier 统一入口）。

    identifier 为邮箱或手机号（后端自动识别）；password 为明文密码。
    """

    identifier: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    """忘记密码：向邮箱发送 reset_password 验证码（防枚举：恒返回成功）。"""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """重置密码：邮箱 + 验证码 + 新密码。成功后撤销该用户全部会话。"""

    email: EmailStr
    code: str = Field(min_length=4, max_length=8)
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    """修改密码（需登录）：验证当前密码后设置新密码。"""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class BindAccountRequest(BaseModel):
    """绑定/换绑手机号或邮箱（需登录）：验证码校验通过后写入。"""

    channel: Literal["phone", "email"]
    target: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=4, max_length=8)
    # 未绑定时 bind_*；已绑定换新时 change_*（前端按当前绑定状态选择）
    purpose: Literal["bind_phone", "change_phone", "bind_email", "change_email"] = (
        "bind_phone"
    )


class BindAccountResponse(BaseModel):
    """绑定结果。"""

    success: bool = True
    channel: str
    target: str  # 归一化后的值


class UpdateProfileRequest(BaseModel):
    """更新基本资料（需登录）。"""

    real_name: str | None = Field(default=None, min_length=1, max_length=64)
    company: str | None = Field(default=None, max_length=128)


class AccountProfileResponse(BaseModel):
    """用户中心账户资料（含验证状态与偏好）。"""

    id: UUID
    username: str
    real_name: str | None = None
    email: str | None = None
    email_verified: bool = False
    phone: str | None = None
    phone_verified: bool = False
    company: str | None = None
    role: str
    plan_tier: str = "free"
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    has_password: bool = False

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    """持久化会话（refresh token）信息。"""

    id: str
    issued_at: datetime
    expires_at: datetime
    user_agent: str | None = None
    ip_address: str | None = None
    device_id: str | None = None


class SessionListResponse(BaseModel):
    """会话列表。"""

    sessions: list[SessionOut]
