"""手机号规范化工具。

目标: 13800138000 / +8613800138000 / 008613800138000 / 86 13800138000
      → 统一 +8613800138000

规则:
1. 去掉所有空格 / 横线 / 括号
2. 匹配前缀: +86 / 86 / 0086 → 全部归一为 +86
3. 中国大陆手机号 11 位, 以 1 开头
4. 其他国家暂时不在本轮范围 (先按 + 国家码 + 号码处理, 落库原样)
"""
from __future__ import annotations

import re

from app.core.errors import ValidationError

# 中国大陆: +86 + 11 位数字
_CN_MOBILE_RE = re.compile(r"^(?:\+?86|0086)?1[3-9]\d{9}$")

# 已格式化的国际号码: + 国家码 1-3 位 + 数字 4-14 位
_INTL_RE = re.compile(r"^\+([1-9]\d{0,2})(\d{4,14})$")


def normalize_phone(raw: str) -> str:
    """把任意格式手机号统一为 E.164 形式。

    Raises:
        ValidationError: 格式非法
    """
    if not raw:
        raise ValidationError("手机号不能为空")

    # 1. 清掉空白 / 横线 / 括号
    cleaned = re.sub(r"[\s\-\(\)]", "", raw)

    # 2. 中国大陆
    if _CN_MOBILE_RE.match(cleaned):
        # 取最后 11 位
        last11 = cleaned[-11:]
        return f"+86{last11}"

    # 3. 已是 + 开头, 校验国际号
    if cleaned.startswith("+"):
        m = _INTL_RE.match(cleaned)
        if m:
            return cleaned
        raise ValidationError("手机号格式不正确")

    # 4. 0 开头 (如 0086...) - 转成 +
    if cleaned.startswith("00"):
        candidate = "+" + cleaned[2:]
        m = _INTL_RE.match(candidate)
        if m:
            return candidate
        raise ValidationError("手机号格式不正确")

    # 5. 裸 11 位中国号 (没前缀)
    if re.match(r"^1[3-9]\d{9}$", cleaned):
        return f"+86{cleaned}"

    raise ValidationError("手机号格式不正确")


def mask_phone(phone: str) -> str:
    """脱敏: +8613800****00"""
    if not phone or len(phone) < 7:
        return "***"
    if phone.startswith("+86") and len(phone) >= 13:
        return f"+86 {phone[3:7]}****{phone[-2:]}"
    return phone[:3] + "****" + phone[-2:]
