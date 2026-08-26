"""Pydantic Schema 集合。"""

from app.schemas.common import Page, PageMeta, TraceEnvelope
from app.schemas.document import (
    AttachmentItem,
    DocumentJson,
    DocumentRead,
    DocumentUploadResponse,
    ParagraphItem,
)
from app.schemas.notification import (
    NotificationListResponse,
    NotificationRead,
    NotificationUnreadCount,
)
from app.schemas.search import (
    SearchDocumentHit,
    SearchReportHit,
    SearchResponse,
    SearchTaskHit,
)
from app.schemas.task import (
    FeedbackRequest,
    ReviewTriggerRequest,
    TaskCreate,
    TaskRead,
    TaskStatusResponse,
)
from app.schemas.user_feedback import (
    TargetKind,
    UserFeedbackCreate,
    UserFeedbackListResponse,
    UserFeedbackRead,
    UserFeedbackSummary,
    UserFeedbackUpdate,
    Vote,
)

__all__ = [
    "AttachmentItem",
    "DocumentJson",
    "DocumentRead",
    "DocumentUploadResponse",
    "FeedbackRequest",
    "NotificationListResponse",
    "NotificationRead",
    "NotificationUnreadCount",
    "Page",
    "PageMeta",
    "ParagraphItem",
    "ReviewTriggerRequest",
    "SearchDocumentHit",
    "SearchReportHit",
    "SearchResponse",
    "SearchTaskHit",
    "TargetKind",
    "TaskCreate",
    "TaskRead",
    "TaskStatusResponse",
    "TraceEnvelope",
    "UserFeedbackCreate",
    "UserFeedbackListResponse",
    "UserFeedbackRead",
    "UserFeedbackSummary",
    "UserFeedbackUpdate",
    "Vote",
]
