"""ORM 模型集合 - 集中导入便于 Alembic autogenerate 发现。"""

from app.models.contract import ContractReview
from app.models.document import Document
from app.models.identity import (
    AccountLinkPending,
    OAuthIdentity,
    RateLimitBucket,
    RefreshToken,
    UserAcquisitionSource,
    UserEvent,
    UserLoginEvent,
    VerificationCode,
)
from app.models.legal import LegalClause, LegalDocument, LegalSource
from app.models.notification import Notification
from app.models.platform import (
    AuditRecord,
    EvalRun,
    FeedbackCase,
    GoldenDataset,
    Prompt,
)
from app.models.research import ResearchSession
from app.models.task import AgentLog, ReviewResult, ReviewTask
from app.models.user import Order, Organization, Payment, User, UserPlan
from app.models.user_feedback import UserFeedback
from app.models.workspace import DocumentChunk, DocumentVersion, Project

__all__ = [
    "AccountLinkPending",
    "AgentLog",
    "AuditRecord",
    "ContractReview",
    "Document",
    "DocumentChunk",
    "DocumentVersion",
    "EvalRun",
    "FeedbackCase",
    "GoldenDataset",
    "LegalClause",
    "LegalDocument",
    "LegalSource",
    "Notification",
    "OAuthIdentity",
    "Order",
    "Organization",
    "Payment",
    "Project",
    "Prompt",
    "RateLimitBucket",
    "RefreshToken",
    "ResearchSession",
    "ReviewResult",
    "ReviewTask",
    "User",
    "UserAcquisitionSource",
    "UserEvent",
    "UserFeedback",
    "UserLoginEvent",
    "UserPlan",
    "VerificationCode",
]
