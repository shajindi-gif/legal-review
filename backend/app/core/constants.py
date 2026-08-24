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
    FREE = "free"                # 免费版：每天 3 次审查
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
