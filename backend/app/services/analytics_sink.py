"""商业化埋点写入助手（服务端，best-effort）。

用于在非 HTTP 上下文（如 LangGraph 工作流）中构造/写入关键转化事件。
所有写库路径都必须 best-effort：失败只记日志，绝不抛异常影响主流程。
"""

from __future__ import annotations

from uuid import UUID

from app.models.analytics import AnalyticsEvent


def build_task_completed_event(
    *,
    user_id: UUID | None,
    task_id: UUID,
    nodes_completed: set[str] | frozenset[str],
) -> AnalyticsEvent | None:
    """构造 task_completed 埋点事件；仅当报告已生成时才返回事件（否则 None）。

    - 口径：report_generation 节点完成 = 审查交付完成，用于激活率分母/分子对齐。
    - 返回 None 表示本次工作流未产出报告，不应计入 completed。
    """
    if "report_generation" not in nodes_completed:
        return None
    return AnalyticsEvent(
        user_id=user_id,
        event="task_completed",
        properties={
            "task_id": str(task_id),
            "nodes_completed": len(nodes_completed),
            "human_review": "human_review" in nodes_completed,
        },
    )
