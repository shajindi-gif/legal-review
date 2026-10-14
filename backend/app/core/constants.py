"""全局常量与枚举。

集中管理业务状态/角色/枚举，避免硬编码散落各处。
"""

from __future__ import annotations

from enum import StrEnum


# ============== 用户角色 ==============
class UserRole(StrEnum):
    SUBMITTER = "submitter"        # 送审人
    REVIEWER = "reviewer"           # 审查员
    SUPERVISOR = "supervisor"       # 审查主管
    ADMIN = "admin"                 # 系统管理员
    LIBRARIAN = "librarian"         # 法规库管理员


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"


# ============== SaaS 订阅 ==============
class PlanTier(StrEnum):
    FREE = "free"                # 免费版：累计 2 次体验（用尽后需升级）
    PRO = "pro"                  # 专业版：299/月，无限审查
    ENTERPRISE = "enterprise"    # 企业版：1999/月，团队账号


class SubscriptionStatus(StrEnum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    CLOSED = "closed"


# ============== 支付渠道 ==============
class PaymentChannel(StrEnum):
    WECHAT = "wechat"    # 微信支付（V3）
    ALIPAY = "alipay"    # 支付宝（RSA2）


class PayScene(StrEnum):
    """支付场景（按设备 / 环境分流，前端检测后传入）。

    - NATIVE：电脑扫码（微信 Native 二维码）
    - JSAPI：微信内 H5 调起（需 openid）
    - H5：手机浏览器跳转（微信 H5）
    - PAGE：电脑网页跳转（支付宝电脑网站支付）
    - WAP：手机网页跳转（支付宝手机网站支付）
    """

    NATIVE = "native"
    JSAPI = "jsapi"
    H5 = "h5"
    PAGE = "page"
    WAP = "wap"


# 各渠道允许的支付场景
CHANNEL_SCENES: dict[PaymentChannel, tuple[PayScene, ...]] = {
    PaymentChannel.WECHAT: (PayScene.NATIVE, PayScene.JSAPI, PayScene.H5),
    PaymentChannel.ALIPAY: (PayScene.PAGE, PayScene.WAP),
}


# ============== 套餐定价（单位：分，避免浮点误差）==============
# key = PlanTier，value = {周期天数: 价格分}
# 299 元/月（Pro）、1999 元/月（Enterprise）
PLAN_PRICING_CENTS: dict[str, dict[int, int]] = {
    PlanTier.PRO: {
        30: 29900,        # 299 元 / 月
        90: 83700,        # 279 元 / 月（季付 93 折）
        365: 299000,      # 约 249 元 / 月（年付送 2 个月）
    },
    PlanTier.ENTERPRISE: {
        30: 199900,       # 1999 元 / 月
    },
}

# 免费版累计体验次数（用尽后需升级套餐，不再每日重置）
FREE_TRIAL_LIMIT = 2

# 各套餐开通后的审查配额（-1 = 不限；Free 走 FREE_TRIAL_LIMIT 累计体验计数）
PLAN_QUOTA_DAILY: dict[str, int] = {
    PlanTier.PRO: -1,
    PlanTier.ENTERPRISE: -1,
}


# ============== 单位类型 ==============
class OrganizationType(StrEnum):
    COUNTY_DEPT = "county_dept"     # 县直部门
    TOWNSHIP = "township"            # 乡镇
    STREET = "street"                # 街道
    PUBLIC_INST = "public_inst"     # 公共机构
    STATE_OWNED = "state_owned"     # 国有单位
    PERSONAL = "personal"           # 个人虚拟组织(Free 用户独立送审)


# ============== 文件 ==============
class FileType(StrEnum):
    DOCX = "docx"
    PDF = "pdf"
    IMAGE = "image"
    TXT = "txt"


class ParseStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    DONE = "done"
    FAILED = "failed"


# ============== 任务状态 ==============
class TaskStatus(StrEnum):
    CREATED = "created"
    PARSING = "parsing"
    CLASSIFYING = "classifying"
    REVIEWING = "reviewing"
    VERIFYING = "verifying"
    REPORTING = "reporting"
    HUMAN_REVIEW = "human_review"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# ============== 法规库 ==============
class LawType(StrEnum):
    LAW = "law"                     # 法律
    ADMIN_REG = "admin_reg"         # 行政法规
    LOCAL_REG = "local_reg"         # 地方性法规
    RULE = "rule"                   # 规章
    POLICY = "policy"               # 政策文件
    JUDICIAL = "judicial"           # 司法解释


class LawLevel(StrEnum):
    NATIONAL = "national"
    PROVINCE = "province"
    CITY = "city"
    COUNTY = "county"


class LawStatus(StrEnum):
    DRAFT = "draft"
    EFFECTIVE = "effective"
    AMENDED = "amended"
    REPEALED = "repealed"
    EXPIRED = "expired"


# ============== Agent / 节点 ==============
class NodeStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    RETRY = "retry"
    SKIPPED = "skipped"


class AgentName(StrEnum):
    """9 个审核 Agent + Supervisor。"""
    SUPERVISOR = "supervisor"
    DOC_PARSE = "doc_parse"
    DOC_CLASSIFY = "doc_classify"
    LEGAL_RETRIEVE = "legal_retrieve"
    AUTHORITY_REVIEW = "authority_review"
    PROCEDURE_REVIEW = "procedure_review"
    CONTENT_REVIEW = "content_review"
    RISK_ASSESSMENT = "risk_assessment"
    EVIDENCE_VERIFY = "evidence_verify"
    REPORT_GENERATION = "report_generation"
    HUMAN_REVIEW = "human_review"
    HUMAN_FALLBACK = "human_fallback"


class OverallStatus(StrEnum):
    PASS = "pass"
    RISK = "risk"
    FAIL = "fail"


# ============== 风险维度 ==============
class RiskDimension(StrEnum):
    AUTHORITY = "authority"         # 主体合法性
    PROCEDURE = "procedure"         # 程序完整性
    CONTENT = "content"             # 内容合法性
    PROHIBITION = "prohibition"     # 禁止性规定
    INTEREST = "interest"           # 权益影响


class RiskSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============== 审计动作 ==============
class AuditAction(StrEnum):
    CREATE = "create"
    UPLOAD = "upload"
    REVIEW = "review"
    MODIFY = "modify"
    SIGN = "sign"
    DELETE = "delete"


# ============== Prompt 状态 ==============
class PromptStatus(StrEnum):
    DRAFT = "draft"
    EVALUATING = "evaluating"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


# ============== Golden Dataset 类别 ==============
class GoldenCategory(StrEnum):
    NORMAL = "normal"
    AUTHORITY_VIOLATION = "authority_violation"
    PROCEDURE_MISSING = "procedure_missing"
    CONTENT_VIOLATION = "content_violation"
    BOUNDARY = "boundary"
    NON_NORMATIVE = "non_normative"
