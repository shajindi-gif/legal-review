"""通知写入服务 - 节点事件 → Notification 表。

来自 UI-M8：审查节点进度（running/done）通知。
使用方式：在 trigger_doc_parse_background 中以 astream 收每节点更新，
调用 emit_node_running / emit_node_done 各一次。
所有写入用新 session，与触发器的 session 隔离（不让节点异常影响通知）。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.notification import NotificationService

logger = get_logger("notifier")


NODE_LABEL_ZH: dict[str, str] = {
    "doc_parse": "文件解析",
    "doc_classify": "文件分类",
    "legal_retrieve": "法规检索",
    "authority_review": "主体审查",
    "procedure_review": "程序审查",
    "content_review": "内容审查",
    "risk_assessment": "风险评估",
    "evidence_verify": "证据校验",
    "report_generation": "报告生成",
    "human_review": "人工复核",
    "human_fallback": "人工兜底",
}


def _label(node_name: str) -> str:
    return NODE_LABEL_ZH.get(node_name, node_name)


async def emit_node_running(
    db: AsyncSession,
    *,
    recipient_id: UUID,
    task_id: UUID,
    node_name: str,
    iteration: int = 0,
) -> None:
    """节点开始运行时发出通知。"""
    label = _label(node_name)
    try:
        await NotificationService.create(
            db,
            recipient_id=recipient_id,
            kind="node_running",
            title=f"节点「{label}」开始运行",
            body=f"任务 {str(task_id)[:8]} 进入 {label} 阶段",
            task_id=task_id,
            link=f"/review/{task_id}",
            payload={"node": node_name, "iteration": iteration, "status": "running"},
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning(
            "notify_node_running_failed",
            task_id=str(task_id),
            node=node_name,
            error=str(e),
        )


async def emit_node_done(
    db: AsyncSession,
    *,
    recipient_id: UUID,
    task_id: UUID,
    node_name: str,
    iteration: int = 0,
) -> None:
    """节点运行完成时发出通知。"""
    label = _label(node_name)
    try:
        await NotificationService.create(
            db,
            recipient_id=recipient_id,
            kind="node_done",
            title=f"节点「{label}」已完成",
            body=f"任务 {str(task_id)[:8]} 的 {label} 阶段已完成",
            task_id=task_id,
            link=f"/review/{task_id}",
            payload={"node": node_name, "iteration": iteration, "status": "done"},
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning(
            "notify_node_done_failed",
            task_id=str(task_id),
            node=node_name,
            error=str(e),
        )
