"""评测服务 - Sprint 5 / FR-029/031 评测体系 + 6 大指标。

职责：
1. GoldenDatasetService: 评测集导入/查询/删除
2. EvalRunner: 运行 Golden Dataset 评测，计算 6 大指标
3. EvalMetrics: 评测指标数据类（parse_acc/retrieval_acc/citation_acc/risk_kappa/
   report_complete/hallucination_rate/overall_pass）

硬约束：
- Prompt 变更必须过评测门控（overall_pass + pass_rate >= min_eval_pass_rate）
- 评测结果写入 eval_runs 表
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GoldenCategory
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.platform import EvalRun, GoldenDataset
from app.schemas.eval import (
    GoldenBatchImportResponse,
    GoldenCaseCreate,
)

logger = get_logger("services.eval_runner")


# ============== EvalMetrics ==============
@dataclass
class EvalMetrics:
    """6 大评测指标（单条 Case 级）。"""

    parse_acc: float = 0.0
    retrieval_acc: float = 0.0
    citation_acc: float = 0.0
    risk_kappa: float = 0.0
    report_complete: float = 0.0
    hallucination_rate: float = 0.0

    @property
    def overall_pass(self) -> bool:
        """全部达标 → True。"""
        return (
            self.parse_acc >= 0.95
            and self.retrieval_acc >= 0.90
            and self.citation_acc >= 0.85
            and self.risk_kappa >= 0.90
            and self.report_complete >= 1.0
            and self.hallucination_rate <= 0.05
        )


@dataclass
class _AggMetrics:
    """多 Case 聚合指标。"""

    parse_accs: list[float] = field(default_factory=list)
    retrieval_accs: list[float] = field(default_factory=list)
    citation_accs: list[float] = field(default_factory=list)
    risk_statuses: list[tuple[str, str]] = field(default_factory=list)  # (actual, expected)
    report_completes: list[float] = field(default_factory=list)
    hallucination_rates: list[float] = field(default_factory=list)

    def aggregate(self) -> EvalMetrics:
        """聚合为 EvalMetrics。"""

        def _avg(lst: list[float]) -> float:
            return sum(lst) / len(lst) if lst else 0.0

        return EvalMetrics(
            parse_acc=_avg(self.parse_accs),
            retrieval_acc=_avg(self.retrieval_accs),
            citation_acc=_avg(self.citation_accs),
            risk_kappa=_cohen_kappa(self.risk_statuses),
            report_complete=_avg(self.report_completes),
            hallucination_rate=_avg(self.hallucination_rates),
        )


# ============== 指标计算函数 ==============
def _field_f1(actual: dict[str, Any], expected: dict[str, Any]) -> float:
    """文件解析准确率：字段 F1。

    比较 actual 与 expected 的顶层字段是否匹配。
    """
    actual_keys = set(actual.keys())
    expected_keys = set(expected.keys())
    if not expected_keys:
        return 1.0
    # precision: 实际字段中有多少在期望中
    # recall: 期望字段中有多少在实际中
    tp = len(actual_keys & expected_keys)
    precision = tp / len(actual_keys) if actual_keys else 0.0
    recall = tp / len(expected_keys)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _retrieval_recall(
    actual_context: list[dict[str, Any]],
    expected_risks: list[dict[str, Any]],
) -> float:
    """法规检索准确率：Top-10 召回率。

    expected_risks 中的 law_name+article 在 actual_context 中命中多少。
    """
    if not expected_risks:
        return 1.0
    expected_set = {
        (r.get("law_name", ""), r.get("article", "")) for r in expected_risks
    }
    actual_set = {
        (c.get("law_name", ""), c.get("article", "")) for c in actual_context
    }
    hit = len(expected_set & actual_set)
    return hit / len(expected_set)


def _citation_accuracy(
    actual_evidences: list[dict[str, Any]],
    expected_evidences: list[dict[str, Any]],
) -> float:
    """条款引用准确率：正确引用数 / 总引用数。"""
    if not actual_evidences:
        return 1.0 if not expected_evidences else 0.0
    expected_set = {
        (e.get("law_name", ""), e.get("article", "")) for e in expected_evidences
    }
    correct = sum(
        1
        for e in actual_evidences
        if (e.get("law_name", ""), e.get("article", "")) in expected_set
    )
    return correct / len(actual_evidences)


def _cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's Kappa 一致性。

    pairs: [(actual_status, expected_status), ...]
    """
    if not pairs:
        return 0.0
    n = len(pairs)
    # 观察一致性
    p_o = sum(1 for a, e in pairs if a == e) / n
    # 期望一致性
    labels = {a for a, _ in pairs} | {e for _, e in pairs}
    p_e = 0.0
    for label in labels:
        p_a = sum(1 for a, _ in pairs if a == label) / n
        p_e_val = sum(1 for _, e in pairs if e == label) / n
        p_e += p_a * p_e_val
    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1 - p_e)


def _report_completeness(report_markdown: str) -> float:
    """报告完整性：7 章节必填字段完整率。"""
    required_sections = [
        "一、文件基本情况",
        "二、审查依据",
        "三、审核过程",
        "四、发现问题",
        "五、风险等级",
        "六、修改建议",
        "七、审查意见",
    ]
    if not report_markdown:
        return 0.0
    found = sum(1 for s in required_sections if s in report_markdown)
    return found / len(required_sections)


def _hallucination_rate(risks: list[dict[str, Any]]) -> float:
    """幻觉率：无依据判断比例。

    risks 中 law_name 为空或无 evidence 的比例。
    """
    if not risks:
        return 0.0
    no_evidence = sum(
        1
        for r in risks
        if not r.get("law_name") or not r.get("article")
    )
    return no_evidence / len(risks)


def compute_case_metrics(actual: dict[str, Any], expected: dict[str, Any]) -> EvalMetrics:
    """计算单条 Case 的 6 大指标。

    actual: Agent 全链输出（document_json + legal_context + agent outputs + report）
    expected: Golden Case expected_json
    """
    return EvalMetrics(
        parse_acc=_field_f1(
            actual.get("document_json", {}),
            expected.get("document_json", expected),
        ),
        retrieval_acc=_retrieval_recall(
            actual.get("legal_context", []),
            expected.get("risks", []),
        ),
        citation_acc=_citation_accuracy(
            actual.get("evidences", []),
            expected.get("risks", []),
        ),
        risk_kappa=1.0 if actual.get("overall_status") == expected.get("overall_status") else 0.0,
        report_complete=_report_completeness(actual.get("report_markdown", "")),
        hallucination_rate=_hallucination_rate(actual.get("risks", [])),
    )


# ============== GoldenDatasetService ==============
class GoldenDatasetService:
    """Golden Dataset 评测集管理。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def batch_import(
        self, cases: list[GoldenCaseCreate],
    ) -> GoldenBatchImportResponse:
        """批量导入 Golden Cases（容错）。"""
        success = 0
        failed = 0
        errors: list[str] = []
        for i, case in enumerate(cases):
            try:
                record = GoldenDataset(
                    case_name=case.case_name,
                    category=case.category,
                    input_file_path=case.input_file_path,
                    expected_json=case.expected_json,
                    expected_status=case.expected_status,
                    notes=case.notes,
                )
                self._session.add(record)
                await self._session.flush()
                success += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append(f"case[{i}] {case.case_name}: {e}")
                await self._session.rollback()
        await self._session.commit()
        return GoldenBatchImportResponse(
            total=len(cases), success=success, failed=failed, errors=errors,
        )

    async def list_cases(
        self, category: str | None = None,
    ) -> list[GoldenDataset]:
        """查询评测集（可选 category 过滤）。"""
        stmt = select(GoldenDataset).order_by(GoldenDataset.created_at.desc())
        if category:
            stmt = stmt.where(GoldenDataset.category == category)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_case(self, case_id: UUID) -> GoldenDataset:
        """查询单条。"""
        stmt = select(GoldenDataset).where(GoldenDataset.id == case_id)
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundError("GoldenDataset", str(case_id))
        return record

    async def delete_case(self, case_id: UUID) -> None:
        """删除单条。"""
        case = await self.get_case(case_id)
        await self._session.delete(case)
        await self._session.commit()

    async def count(self) -> int:
        """统计总数。"""
        from sqlalchemy import func

        stmt = select(func.count(GoldenDataset.id))
        result = await self._session.execute(stmt)
        return result.scalar_one()


# ============== EvalRunner ==============
class EvalRunner:
    """评测运行器 - 跑 Golden Dataset 评测。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._dataset_svc = GoldenDatasetService(session)

    async def run(
        self,
        *,
        prompt_version: str,
        categories: list[GoldenCategory] | None = None,
        max_cases: int | None = None,
        case_runner: Any | None = None,
    ) -> EvalRun:
        """运行评测。

        Args:
            prompt_version: 被评测的 Prompt 版本
            categories: 可选类别过滤
            max_cases: 最大评测条数
            case_runner: 可注入的 case 执行器（测试用），签名
                async fn(case: GoldenDataset) -> dict[str, Any]
                生产环境默认为 None（需接入 LangGraph 流程）
        """
        run_uuid = uuid4()
        started = datetime.utcnow()

        # 1. 加载评测集
        cases = await self._dataset_svc.list_cases()
        if categories:
            cat_set = {str(c) for c in categories}
            cases = [c for c in cases if c.category in cat_set]
        if max_cases:
            cases = cases[:max_cases]

        if not cases:
            raise ValidationError("评测集为空，无法运行评测")

        # 2. 逐条评测
        agg = _AggMetrics()
        for case in cases:
            if case_runner is not None:
                actual = await case_runner(case)
            else:
                # 无执行器时用 expected 作为 mock（仅用于框架测试）
                actual = case.expected_json

            metrics = compute_case_metrics(actual, case.expected_json)
            agg.parse_accs.append(metrics.parse_acc)
            agg.retrieval_accs.append(metrics.retrieval_acc)
            agg.citation_accs.append(metrics.citation_acc)
            agg.risk_statuses.append(
                (actual.get("overall_status", "unknown"), case.expected_status)
            )
            agg.report_completes.append(metrics.report_complete)
            agg.hallucination_rates.append(metrics.hallucination_rate)

        # 3. 聚合
        final = agg.aggregate()
        finished = datetime.utcnow()

        # 4. 写入 eval_runs
        record = EvalRun(
            run_id=run_uuid,
            prompt_version=prompt_version,
            started_at=started,
            finished_at=finished,
            total_cases=len(cases),
            parse_acc=round(final.parse_acc, 4),
            retrieval_acc=round(final.retrieval_acc, 4),
            citation_acc=round(final.citation_acc, 4),
            risk_kappa=round(final.risk_kappa, 4),
            report_complete=round(final.report_complete, 4),
            hallucination_rate=round(final.hallucination_rate, 4),
            overall_pass=final.overall_pass,
        )
        self._session.add(record)
        await self._session.commit()

        logger.info(
            "eval_run_done",
            run_id=str(run_uuid), prompt_version=prompt_version,
            total_cases=len(cases), overall_pass=final.overall_pass,
        )
        return record

    async def get_run(self, run_id: UUID) -> EvalRun:
        """查询评测记录。"""
        stmt = select(EvalRun).where(EvalRun.run_id == run_id)
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundError("EvalRun", str(run_id))
        return record

    async def list_runs(self, limit: int = 20) -> list[EvalRun]:
        """评测记录列表。"""
        stmt = (
            select(EvalRun)
            .order_by(EvalRun.started_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def check_gate(
        metrics: EvalMetrics, min_pass_rate: float = 0.9,
    ) -> bool:
        """评测门控判断。

        overall_pass 且 pass_rate >= min_pass_rate。
        """
        return metrics.overall_pass
