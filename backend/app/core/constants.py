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

# 账户锁定策略（R2-1）：连续密码错误达到阈值后锁定，到期自动解锁
MAX_FAILED_LOGIN_ATTEMPTS = 5
FAILED_LOGIN_LOCKOUT_MINUTES = 15

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


# ============== 统一工作台（Workspace）==============
class ProjectType(StrEnum):
    LEGAL_RESEARCH = "legal_research"      # 法律研究
    CONTRACT_REVIEW = "contract_review"    # 合同审查
    GOV_REVIEW = "gov_review"              # 规范性文件合法性审核
    DOCUMENT_DRAFT = "document_draft"      # 文书起草


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"


class DocumentVersionStatus(StrEnum):
    DRAFT = "draft"
    FINAL = "final"
    SUPERSEDED = "superseded"


# ============== 法律研究 ==============
class ResearchStatus(StrEnum):
    DRAFT = "draft"
    COMPLETED = "completed"
    FAILED = "failed"


# ============== 合同审查 ==============
class ReviewStance(StrEnum):
    """审查立场（对照修改视图的视角）。"""

    PARTY_A = "party_a"    # 甲方立场
    PARTY_B = "party_b"    # 乙方立场
    NEUTRAL = "neutral"    # 中立


class ContractRiskLevel(StrEnum):
    """合同风险分级（5 档，含 INFO 提示项）。"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ContractReviewStatus(StrEnum):
    PENDING = "pending"
    REVIEWING = "reviewing"
    DONE = "done"
    FAILED = "failed"


CONTRACT_RISK_LEVEL_ORDER: dict[str, int] = {
    ContractRiskLevel.CRITICAL: 0,
    ContractRiskLevel.HIGH: 1,
    ContractRiskLevel.MEDIUM: 2,
    ContractRiskLevel.LOW: 3,
    ContractRiskLevel.INFO: 4,
}


# ============== 权威数据源（合规登记）==============
class LegalSourceType(StrEnum):
    OFFICIAL_DB = "official_db"    # 官方数据库（如国家法律法规数据库）
    GOV_PORTAL = "gov_portal"      # 政府门户网站
    LOCAL_GOV = "local_gov"        # 地方人大/政府
    OPEN_DATA = "open_data"        # 开放数据平台
    MANUAL = "manual"              # 人工录入


class SourceAuthorizationStatus(StrEnum):
    """数据源合规状态：未核实前一律 UNKNOWN，禁止宣称 READY。"""

    VERIFIED = "verified"        # 已核实可合规访问（robots/条款允许）
    RESTRICTED = "restricted"    # 受限（需授权/登录）
    PROHIBITED = "prohibited"    # 禁止抓取
    UNKNOWN = "unknown"          # 未核实


# ============== 规范性文件合法性审核（Government Legal Review）==============
class GovReviewDimension(StrEnum):
    """审核维度 A~J（指令第六条）。每一维度对应一类审核规则。"""

    AUTHORITY = "A"          # 制定主体与权限审核
    SUPERIOR_LAW = "B"       # 上位法一致性审核
    ADMIN_POWER = "C"        # 行政权力设定审核（许可/处罚/强制/征收/收费）
    RIGHTS_DUTIES = "D"      # 权利义务审核（不得违法增义务/减权益）
    PROCEDURE = "E"          # 程序合法性审核
    FAIR_COMPETITION = "F"   # 公平竞争审查
    BUSINESS_ENV = "G"       # 营商环境与市场准入风险
    VALIDITY = "H"           # 法律依据时效性审核
    FORMAL = "I"             # 文件形式与条款规范审核
    LOCAL_RULE = "J"         # 地方特别规则审核


GOV_DIMENSION_LABELS: dict[str, str] = {
    GovReviewDimension.AUTHORITY: "制定主体与权限",
    GovReviewDimension.SUPERIOR_LAW: "上位法一致性",
    GovReviewDimension.ADMIN_POWER: "行政权力设定",
    GovReviewDimension.RIGHTS_DUTIES: "权利义务",
    GovReviewDimension.PROCEDURE: "程序合法性",
    GovReviewDimension.FAIR_COMPETITION: "公平竞争审查",
    GovReviewDimension.BUSINESS_ENV: "营商环境与市场准入",
    GovReviewDimension.VALIDITY: "法律依据时效性",
    GovReviewDimension.FORMAL: "文件形式与条款规范",
    GovReviewDimension.LOCAL_RULE: "地方特别规则",
}

GOV_DIMENSION_ORDER: dict[str, int] = {
    GovReviewDimension.AUTHORITY: 0,
    GovReviewDimension.SUPERIOR_LAW: 1,
    GovReviewDimension.ADMIN_POWER: 2,
    GovReviewDimension.RIGHTS_DUTIES: 3,
    GovReviewDimension.PROCEDURE: 4,
    GovReviewDimension.FAIR_COMPETITION: 5,
    GovReviewDimension.BUSINESS_ENV: 6,
    GovReviewDimension.VALIDITY: 7,
    GovReviewDimension.FORMAL: 8,
    GovReviewDimension.LOCAL_RULE: 9,
}


class GovRiskLevel(StrEnum):
    """规范性文件审核风险等级（5 档）。"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


GOV_RISK_LEVEL_LABELS: dict[str, str] = {
    GovRiskLevel.CRITICAL: "重大风险",
    GovRiskLevel.HIGH: "高风险",
    GovRiskLevel.MEDIUM: "中风险",
    GovRiskLevel.LOW: "低风险",
    GovRiskLevel.INFO: "提示",
}

GOV_RISK_LEVEL_ORDER: dict[str, int] = {
    GovRiskLevel.CRITICAL: 0,
    GovRiskLevel.HIGH: 1,
    GovRiskLevel.MEDIUM: 2,
    GovRiskLevel.LOW: 3,
    GovRiskLevel.INFO: 4,
}


class GovReviewConclusion(StrEnum):
    """审核结论（指令原文 4 类，AI 辅助结果，非法定正式结论）。"""

    NO_OBVIOUS_VIOLATION = "no_obvious_violation"  # 未发现明显违法问题
    NEEDS_REVISION = "needs_revision"              # 存在需要修改的问题
    MAJOR_RISK = "major_risk"                      # 存在重大合法性风险
    INSUFFICIENT_BASIS = "insufficient_basis"      # 依据或材料不足，暂无法判断


GOV_CONCLUSION_LABELS: dict[str, str] = {
    GovReviewConclusion.NO_OBVIOUS_VIOLATION: "未发现明显违法问题",
    GovReviewConclusion.NEEDS_REVISION: "存在需要修改的问题",
    GovReviewConclusion.MAJOR_RISK: "存在重大合法性风险",
    GovReviewConclusion.INSUFFICIENT_BASIS: "依据或材料不足，暂无法判断",
}


class GovRuleReviewStatus(StrEnum):
    """规则包法律审核状态：地方规则包上线前需法律专业人员审核。"""

    PENDING = "pending_legal_review"   # 待法律专业人员审核
    REVIEWED = "reviewed"              # 已审核通过
    DEPRECATED = "deprecated"          # 已废止
