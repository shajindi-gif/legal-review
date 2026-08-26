"""Agent 节点实现 - Sprint 4 完整版（含 LLM 调用 + Prompt 版本化）。

节点清单（按 04_AGENT_GRAPH_DESIGN.md）：
- doc_parse ✅（Sprint 2）
- doc_classify（Sprint 4，文件分类 LLM）
- legal_retrieve ✅（Sprint 3，RAG 混合检索）
- authority_review（Sprint 4，主体审查 LLM）
- procedure_review（Sprint 4，程序审查 LLM）
- content_review（Sprint 4，内容审查 LLM）
- risk_assessment（Sprint 4，综合评级 LLM）
- evidence_verify（Sprint 4，证据校验 LLM）
- report_generation（Sprint 4，报告生成 LLM）
- human_review（Sprint 6，人工复核）
- human_fallback（Sprint 4，超限兜底）

统一流程：
1. bind_trace_id（硬约束：可追溯）
2. 渲染 Prompt（PromptManager.render，Jinja2 严格模式）
3. 调 LLM（complete_json，JSON Mode）
4. 解析为 Pydantic RiskItem/Evidence
5. 封装为 AgentOutput
6. 写入 state + 更新 task 状态
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.agent.state import AgentOutput, Evidence, ReviewState, RiskItem
from app.core.constants import NodeStatus, ParseStatus, TaskStatus
from app.core.errors import AgentError, NotFoundError
from app.core.logging import bind_trace_id, get_logger
from app.db.session import get_session_factory
from app.models.document import Document
from app.models.task import AgentLog, ReviewResult, ReviewTask
from app.services.prompt_manager import get_prompt_manager
from app.services.sandbox import get_sandbox
from app.tools.llm import get_llm_provider
from app.tools.ocr import ocr_image, ocr_pdf_pages
from app.tools.parsers import parse as parse_file
from app.tools.rag import RAGSearchService

logger = get_logger("agent.nodes")


# ============== 辅助函数 ==============
def _coerce_list(value: Any) -> list[Any]:
    """将 LLM 返回的 risks/evidences 字段强制转为 list。

    防护：LLM 偶发返回 string/dict 而非 list，遍历时会触发
    'str' object has no attribute 'get'（_parse_risk_item 内 data.get）。
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _format_legal_context(legal_context: list[dict[str, Any]]) -> str:
    """格式化 RAG 召回的法规条款为 LLM 可读文本。"""
    if not legal_context:
        return "（未召回相关法规）"
    lines: list[str] = []
    for i, item in enumerate(legal_context[:10], 1):  # 最多 10 条
        law_name = item.get("law_name", "未知")
        article_no = item.get("article_no", "")
        chapter = item.get("chapter", "")
        content = item.get("content", "")[:500]  # 截断
        score = item.get("final_score", 0.0)
        lines.append(
            f"{i}. 《{law_name}》{article_no}"
            + (f"（{chapter}）" if chapter else "")
            + f"\n   {content}\n   [相关度 {score:.2f}]"
        )
    return "\n".join(lines)


def _parse_evidence(data: dict[str, Any]) -> Evidence:
    """从 LLM 输出解析 Evidence（Pydantic）。

    防护：data 非 dict 时返回空 Evidence（LLM 偶发返回 string/null）。
    """
    if not isinstance(data, dict):
        return Evidence(law_name="", article="", original_text="", explanation="")
    return Evidence(
        law_name=str(data.get("law_name", "")),
        article=str(data.get("article", "")),
        original_text=str(data.get("original_text", "")),
        explanation=str(data.get("explanation", "")),
    )


def _parse_risk_item(data: dict[str, Any]) -> RiskItem:
    """从 LLM 输出解析 RiskItem（Pydantic）。

    防护：data 非 dict 时返回空 RiskItem。

    UI-M7：读取 LLM 返回的 paragraph_anchor（如 "#p3"），规范化出
    paragraph_id（"p3"），便于前端按段落 ID 做精准联动。
    """
    if not isinstance(data, dict):
        return RiskItem(
            dimension="content", risk_type="", severity="medium",
            evidence=Evidence(law_name="", article="", original_text="", explanation=""),
            confidence=0.0, suggestion="",
        )
    evidence_data = data.get("evidence", {})
    anchor = data.get("paragraph_anchor") or data.get("anchor")
    if isinstance(anchor, str):
        anchor = anchor.strip()
    paragraph_id = None
    if isinstance(anchor, str) and anchor.startswith("#") and len(anchor) > 1:
        paragraph_id = anchor[1:]
    elif isinstance(anchor, str) and anchor:
        paragraph_id = anchor
    return RiskItem(
        dimension=data.get("dimension", "content"),  # type: ignore[arg-type]
        risk_type=str(data.get("risk_type", "")),
        severity=data.get("severity", "medium"),  # type: ignore[arg-type]
        paragraph_id=paragraph_id,
        paragraph_anchor=anchor if isinstance(anchor, str) else None,
        evidence=_parse_evidence(evidence_data) if evidence_data else Evidence(
            law_name="", article="", original_text="", explanation=""
        ),
        confidence=float(data.get("confidence", 0.0)),
        suggestion=str(data.get("suggestion", "")),
    )


def _format_body_text(body_paragraphs: list[Any]) -> str:
    """格式化正文段落（带锚点）为 LLM 可读文本。"""
    if not body_paragraphs:
        return "（无正文）"
    lines: list[str] = []
    for p in body_paragraphs[:20]:  # 最多 20 段
        if isinstance(p, dict):
            anchor = p.get("id", p.get("anchor", ""))
            text = p.get("text", "")
        else:
            anchor = ""
            text = str(p)
        prefix = f"[{anchor}] " if anchor else ""
        lines.append(f"{prefix}{text}")
    return "\n".join(lines)


def _format_body_summary(body_paragraphs: list[Any], max_chars: int = 2000) -> str:
    """正文摘要（截断到 max_chars）。"""
    text = _format_body_text(body_paragraphs)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


async def _run_llm_node(
    state: ReviewState,
    *,
    prompt_key: str,
    variables: dict[str, Any],
    agent_name: str,
    next_node: str,
    task_status: TaskStatus = TaskStatus.REVIEWING,
    max_tokens: int = 4096,
) -> tuple[dict[str, Any], AgentOutput]:
    """统一 LLM 节点流程：渲染 Prompt → LLM JSON → AgentOutput。

    硬约束：
    - trace_id 必填（bind_trace_id）
    - prompt_versions 必填（每个节点写入）
    - Agent 输出 node_status=PASS（LLM 异常则 retry/fail）

    Args:
        max_tokens: LLM 输出上限；report_generation 等长文节点应传 8192+。
    """
    task_id = state["task_id"]
    trace_id = state["trace_id"]
    bind_trace_id(trace_id)
    start = time.monotonic()

    # 1. 渲染 Prompt
    pm = get_prompt_manager()
    prompt = pm.render(prompt_key, variables)
    spec = pm.get_active(prompt_key)

    # 2. 调 LLM（JSON Mode）
    # 注：不传 model=spec.model_name，强制走 tier 路由
    # （provider.tier_models 按 LLM_PROVIDER env 映射 tier→实际模型）。
    # registry.yaml 的 model_name 字段仅作文档参考，不参与运行时路由。
    provider = get_llm_provider()
    try:
        raw = await provider.complete_json(
            prompt,
            temperature=spec.temperature,
            max_tokens=max_tokens,
            trace_id=trace_id,
            tier=spec.model_tier,
        )
    except AgentError as e:
        logger.error(
            "llm_node_failed",
            agent=agent_name, task_id=task_id, error=str(e),
        )
        # LLM 失败 → node_status=RETRY
        duration_ms = int((time.monotonic() - start) * 1000)
        output = AgentOutput(
            agent_name=agent_name,
            node_status=NodeStatus.RETRY,
            confidence=0.0,
            raw_json={"error": str(e)},
            duration_ms=duration_ms,
            iteration=state.get("iteration", 0),
        )
        if "prompt_versions" not in state:
            state["prompt_versions"] = {}
        state["prompt_versions"][agent_name] = spec.version
        return {"error": str(e)}, output

    # 3. 构造 AgentOutput
    duration_ms = int((time.monotonic() - start) * 1000)
    # 防护：LLM 偶发返回顶层非 dict 的 JSON（如字符串/列表），
    # 统一包装成 dict，避免后续 .get() 调用失败
    if not isinstance(raw, dict):
        raw = {"_raw": raw}
    confidence = float(raw.get("confidence", 0.7))
    node_status = NodeStatus.PASS

    # 如果 LLM 返回 status，映射到 node_status
    raw_status = raw.get("status")
    if raw_status == "FAIL":
        node_status = NodeStatus.FAIL
    elif raw_status == "RETRY":
        node_status = NodeStatus.RETRY

    output = AgentOutput(
        agent_name=agent_name,
        node_status=node_status,
        confidence=confidence,
        raw_json=raw,
        duration_ms=duration_ms,
        iteration=state.get("iteration", 0),
    )

    # 4. 写入 prompt_versions（硬约束）
    if "prompt_versions" not in state:
        state["prompt_versions"] = {}
    state["prompt_versions"][agent_name] = spec.version

    # 5. 持久化：更新任务 + 写审查结果 + 写 agent 日志
    async with get_session_factory()() as db:
        task_result = await db.execute(
            select(ReviewTask).where(ReviewTask.id == UUID(task_id))
        )
        task = task_result.scalar_one_or_none()
        if task is not None:
            task.current_node = next_node
            task.status = task_status
            # 5a. 审查结果
            db.add(ReviewResult(
                task_id=UUID(task_id),
                agent_name=agent_name,
                iteration=output.iteration,
                node_status=output.node_status,
                output_json=output.raw_json,
                risks=[r.model_dump() for r in output.risks],
                evidences=[e.model_dump() for e in output.evidences],
                confidence=output.confidence,
                duration_ms=output.duration_ms,
            ))
            # 5b. Agent 日志
            usage = raw.get("_usage", {}) if isinstance(raw, dict) else {}
            tokens_in = usage.get("prompt_tokens")
            tokens_out = usage.get("completion_tokens")
            latency_ms = usage.get("latency_ms")
            cost = usage.get("cost_cny")
            # StrEnum 的 .value：若 Enum 未匹配(LLM 返回未注册字符串)，node_status 会是 str，
            # 此时 .value 会 AttributeError。用 str() 统一兼容
            node_status_str = str(output.node_status)
            db.add(AgentLog(
                trace_id=UUID(trace_id),
                task_id=UUID(task_id),
                agent_name=agent_name,
                iteration=output.iteration,
                prompt_version=spec.version,
                tool_name=None,
                input_summary=spec.version,
                output_summary=f"status={node_status_str} risks={len(output.risks)}",
                tokens_in=int(tokens_in) if tokens_in is not None else None,
                tokens_out=int(tokens_out) if tokens_out is not None else None,
                latency_ms=int(latency_ms) if latency_ms is not None else None,
                cost_cny=float(cost) if cost is not None else None,
                status=node_status_str,
            ))
            await db.commit()

    logger.info(
        "llm_node_done",
        agent=agent_name, task_id=task_id,
        duration_ms=duration_ms, confidence=confidence,
        prompt_version=spec.version,
    )
    return raw, output


# ============== doc_parse 节点 ==============
async def doc_parse_node(state: ReviewState) -> ReviewState:
    """文件解析节点 - OCR + 结构化。

    Input: state.task_id, state.document_json (空)
    Output: state.document_json, state.parse_result
    Harness: Context (注入 trace_id)；Security (沙箱读取)
    """
    task_id = state["task_id"]
    trace_id = state["trace_id"]
    bind_trace_id(trace_id)
    start = time.monotonic()

    async with get_session_factory()() as db:
        # 加载任务 + 文件
        task_result = await db.execute(
            select(ReviewTask).where(ReviewTask.id == UUID(task_id))
        )
        task = task_result.scalar_one_or_none()
        if task is None:
            raise NotFoundError("ReviewTask", task_id)

        doc_result = await db.execute(
            select(Document).where(
                Document.task_id == task.id, Document.deleted_at.is_(None)
            )
        )
        document = doc_result.scalar_one_or_none()
        if document is None:
            raise NotFoundError("Document", f"task={task_id}")

        # 沙箱读取文件
        sandbox = get_sandbox()
        abs_path = sandbox.absolute_path(task_id, document.storage_path)

        # 解析
        try:
            # file_type 列是 String，从 DB 读回为 plain str（非 FileType enum）；
            # 用 str() 兼容 enum 与 str 两种情形
            ftype = str(document.file_type)
            parsed = parse_file(abs_path, ftype)

            # 数字 PDF 空段落 → OCR fallback
            if parsed.get("_needs_ocr"):
                if ftype == "pdf":
                    parsed = ocr_pdf_pages(abs_path)
                else:
                    parsed = ocr_image(abs_path)

            # 更新 document.parsed_json + parse_status
            document.parsed_json = parsed
            document.parse_status = ParseStatus.DONE
            task.current_node = "doc_classify"
            task.status = TaskStatus.CLASSIFYING

            await db.commit()
        except AgentError as e:
            document.parse_status = ParseStatus.FAILED
            task.status = TaskStatus.FAILED
            task.current_node = "doc_parse"
            state["error"] = str(e)
            await db.commit()
            logger.error("doc_parse_failed", task_id=task_id, error=str(e))
            return state

    duration_ms = int((time.monotonic() - start) * 1000)
    parse_result = AgentOutput(
        agent_name="doc_parse",
        node_status=NodeStatus.PASS,
        confidence=1.0,
        raw_json=parsed,
        duration_ms=duration_ms,
        iteration=state.get("iteration", 0),
    )
    state["parse_result"] = parse_result
    state["document_json"] = parsed
    logger.info(
        "doc_parse_done",
        task_id=task_id,
        duration_ms=duration_ms,
        paragraphs=len(parsed.get("body_paragraphs", [])),
    )
    return state


# ============== doc_classify 节点 ==============
async def doc_classify_node(state: ReviewState) -> ReviewState:
    """文件分类节点 - 判定是否属于行政规范性文件（4 要素）。

    Input: state.document_json
    Output: state.classify_result + state.is_normative
    Prompt: prompts.doc_classify.v1.0.0
    Eval: 分类准确率 ≥ 90%
    """
    doc_json = state.get("document_json") or {}
    body_paragraphs = doc_json.get("body_paragraphs") or []
    variables = {
        "title": (doc_json.get("title") or "").strip(),
        "issuing_authority": (doc_json.get("issuing_authority") or "").strip(),
        "body_text": _format_body_summary(body_paragraphs),
        "keywords": doc_json.get("keywords") or [],
    }

    raw, output = await _run_llm_node(
        state,
        prompt_key="doc_classify",
        variables=variables,
        agent_name="doc_classify",
        # 实际路由由 classify_router 决定：
        #   is_normative=True→legal_retrieve / False→report_generation
        # 此处仅写入 task.current_node 默认值
        next_node="legal_retrieve",
        task_status=TaskStatus.CLASSIFYING,
    )

    # 解析 evidences
    for e in _coerce_list(raw.get("evidences")):
        output.evidences.append(_parse_evidence(e))

    state["classify_result"] = output
    state["is_normative"] = bool(raw.get("is_normative", False))
    return state


# ============== legal_retrieve 节点 ==============
async def legal_retrieve_node(state: ReviewState) -> ReviewState:
    """法规检索节点 - RAG 混合召回。

    Input:  state.document_json（含 title/keywords/body_paragraphs/policy_domain）
    Output: state.legal_context（List[dict]）+ state.retrieval_result
    Tool:   RAGSearchService（混合检索：向量 + trigram + 元数据过滤）
    Prompt: prompts.legal_query.v1.0.0（生成检索 query，替换 Sprint 3 启发式）
    Harness: Context（注入 document_json）；Security（法规库只读）
    Eval:   Top-10 召回率 ≥ 90%（Golden Dataset）
    """
    task_id = state["task_id"]
    trace_id = state["trace_id"]
    bind_trace_id(trace_id)
    start = time.monotonic()

    doc_json = state.get("document_json") or {}
    if not doc_json:
        state["error"] = "legal_retrieve: document_json empty"
        return state

    # === 1. 用 legal_query Prompt 生成检索 query（Sprint 4 替换启发式）===
    queries = await _generate_legal_queries(doc_json, state)
    # 兜底：Prompt 失败时用启发式（保证图不卡死）
    if not queries:
        queries = _extract_review_queries(doc_json)
        logger.warning(
            "legal_query_prompt_fallback",
            task_id=task_id, heuristic_queries=len(queries),
        )
    logger.info("legal_retrieve_start", task_id=task_id, queries=len(queries))

    # === 2. 调 RAG 混合检索 ===
    async with get_session_factory()() as db:
        rag = RAGSearchService(db)
        all_items: list[dict[str, Any]] = []
        seen_clause_ids: set[str] = set()
        for q in queries:
            try:
                items = await rag.search_simple(q, top_k=10)
                for item in items:
                    cid = str(item.clause_id)
                    if cid in seen_clause_ids:
                        continue
                    seen_clause_ids.add(cid)
                    all_items.append({
                        "clause_id": cid,
                        "law_id": str(item.law_id),
                        "law_name": item.law_name,
                        "law_type": item.law_type,
                        "law_status": item.law_status,
                        "chapter": item.chapter,
                        "section": item.section,
                        "article_no": item.article_no,
                        "article_title": item.article_title,
                        "content": item.content,
                        "keywords": item.keywords,
                        "final_score": item.final_score,
                        "query": q,
                    })
            except Exception as e:
                logger.warning(
                    "legal_retrieve_query_failed",
                    task_id=task_id, query=q, error=str(e),
                )

        # === 3. 更新任务状态 ===
        task_result = await db.execute(
            select(ReviewTask).where(ReviewTask.id == UUID(task_id))
        )
        task = task_result.scalar_one_or_none()
        if task is not None:
            task.current_node = "authority_review"
            task.status = TaskStatus.REVIEWING
            await db.commit()

    duration_ms = int((time.monotonic() - start) * 1000)
    retrieval_result = AgentOutput(
        agent_name="legal_retrieve",
        node_status=NodeStatus.PASS if all_items else NodeStatus.RETRY,
        confidence=min(1.0, len(all_items) / 10.0),
        raw_json={
            "queries": queries,
            "total_clauses": len(all_items),
            "top_score": all_items[0]["final_score"] if all_items else 0.0,
        },
        duration_ms=duration_ms,
        iteration=state.get("iteration", 0),
    )
    state["retrieval_result"] = retrieval_result
    state["legal_context"] = all_items
    logger.info(
        "legal_retrieve_done",
        task_id=task_id,
        total_clauses=len(all_items),
        duration_ms=duration_ms,
    )
    return state


async def _generate_legal_queries(doc_json: dict[str, Any], state: ReviewState) -> list[str]:
    """用 legal_query Prompt 生成 RAG 检索 query（Sprint 4：替换启发式）。

    失败时返回空列表（由调用方走启发式 fallback）。
    硬约束：写入 prompt_versions["legal_query"]。
    """
    body_paragraphs = doc_json.get("body_paragraphs") or []
    variables = {
        "title": doc_json.get("title", ""),
        "issuing_authority": doc_json.get("issuing_authority", ""),
        "policy_domain": doc_json.get("policy_domain", ""),
        "keywords": doc_json.get("keywords") or [],
        "body_paragraphs": body_paragraphs[:5],  # 前 5 段
    }

    try:
        pm = get_prompt_manager()
        prompt = pm.render("legal_query", variables)
        spec = pm.get_active("legal_query")
        provider = get_llm_provider()
        raw = await provider.complete_json(
            prompt,
            temperature=spec.temperature,
            trace_id=state["trace_id"],
            tier=spec.model_tier,
        )
        # 写入 prompt_versions
        if "prompt_versions" not in state:
            state["prompt_versions"] = {}
        state["prompt_versions"]["legal_query"] = spec.version

        queries = raw.get("queries") or []
        # 类型校验 + 去重保序
        seen: set[str] = set()
        unique: list[str] = []
        for q in queries:
            if isinstance(q, str) and q.strip() and q not in seen:
                seen.add(q)
                unique.append(q.strip())
        return unique[:10]  # 最多 10 条
    except Exception as e:
        logger.warning(
            "legal_query_prompt_failed",
            task_id=state.get("task_id"), error=str(e),
        )
        return []


def _extract_review_queries(doc_json: dict[str, Any]) -> list[str]:
    """从文件结构化结果抽取审核问题清单（启发式 fallback）。

    策略：title + keywords + policy_domain + 前 3 段文本
    Sprint 4 由 _generate_legal_queries 替换，本函数仅作兜底。
    """
    queries: list[str] = []

    title = doc_json.get("title")
    if title:
        queries.append(title)

    keywords = doc_json.get("keywords") or []
    for kw in keywords[:5]:  # 最多 5 个关键词
        if isinstance(kw, str) and kw.strip():
            queries.append(kw.strip())

    domain = doc_json.get("policy_domain")
    if domain:
        queries.append(f"{domain} 行政规范性文件")

    # 前 3 段文本作为检索增强（截断到 100 字）
    body = doc_json.get("body_paragraphs") or []
    for p in body[:3]:
        text = p.get("text", "") if isinstance(p, dict) else str(p)
        text = text.strip()
        if text:
            queries.append(text[:100])

    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique[:10]  # 最多 10 个 query


# ============== authority_review 节点 ==============
async def authority_review_node(state: ReviewState) -> ReviewState:
    """主体审查节点 - 检查制定主体是否合法。

    Input: state.document_json.issuing_authority, state.legal_context
    Output: state.authority_result
    Prompt: prompts.authority_review.v1.0.0
    Eval: 主体判断准确率 ≥ 95%
    Harness: Evidence（必须引用《地方组织法》等）
    """
    doc_json = state.get("document_json") or {}
    legal_context = state.get("legal_context") or []
    variables = {
        "issuing_authority": doc_json.get("issuing_authority", ""),
        "doc_title": doc_json.get("title", ""),
        "legal_context": _format_legal_context(legal_context),
    }

    raw, output = await _run_llm_node(
        state,
        prompt_key="authority_review",
        variables=variables,
        agent_name="authority_review",
        # 实际下一节点由 authority_router 决定（PASS→procedure_review / FAIL→report_generation）
        # 这里仅写入 task.current_node 的默认值，路由由 graph.py 控制
        next_node="procedure_review",
    )

    # 解析 risks + evidences
    for r in _coerce_list(raw.get("risks")):
        output.risks.append(_parse_risk_item(r))
    for e in _coerce_list(raw.get("evidences")):
        output.evidences.append(_parse_evidence(e))

    state["authority_result"] = output
    return state


# ============== procedure_review 节点 ==============
async def procedure_review_node(state: ReviewState) -> ReviewState:
    """程序审查节点 - 5 项程序检查。

    Input: state.document_json, state.legal_context
    Output: state.procedure_result
    Prompt: prompts.procedure_review.v1.0.0
    Eval: 程序缺失检出率 ≥ 85%
    """
    doc_json = state.get("document_json") or {}
    legal_context = state.get("legal_context") or []
    body_paragraphs = doc_json.get("body_paragraphs") or []
    variables = {
        "doc_title": doc_json.get("title", ""),
        "issuing_authority": doc_json.get("issuing_authority", ""),
        "body_text": _format_body_summary(body_paragraphs),
        "legal_context": _format_legal_context(legal_context),
    }

    raw, output = await _run_llm_node(
        state,
        prompt_key="procedure_review",
        variables=variables,
        agent_name="procedure_review",
        next_node="content_review",
    )

    # 解析 risks + evidences
    for r in _coerce_list(raw.get("risks")):
        output.risks.append(_parse_risk_item(r))
    for e in _coerce_list(raw.get("evidences")):
        output.evidences.append(_parse_evidence(e))

    state["procedure_result"] = output
    return state


# ============== content_review 节点 ==============
async def content_review_node(state: ReviewState) -> ReviewState:
    """内容审查节点 - 6 类违法情形审查。

    Input: state.document_json.body_paragraphs, state.legal_context
    Output: state.content_result
    Prompt: prompts.content_review.v1.0.0
    Eval: 风险点召回 ≥ 85%，幻觉率 ≤ 5%
    Harness: Evidence（每风险点必含条款原文）；Quality（Verifier 校验）
    """
    doc_json = state.get("document_json") or {}
    legal_context = state.get("legal_context") or []
    body_paragraphs = doc_json.get("body_paragraphs") or []
    variables = {
        "doc_title": doc_json.get("title", ""),
        "body_paragraphs": _format_body_text(body_paragraphs),
        "legal_context": _format_legal_context(legal_context),
    }

    raw, output = await _run_llm_node(
        state,
        prompt_key="content_review",
        variables=variables,
        agent_name="content_review",
        next_node="risk_assessment",
    )

    # 解析 risks + evidences
    for r in _coerce_list(raw.get("risks")):
        output.risks.append(_parse_risk_item(r))
    for e in _coerce_list(raw.get("evidences")):
        output.evidences.append(_parse_evidence(e))

    state["content_result"] = output
    return state


# ============== risk_assessment 节点 ==============
async def risk_assessment_node(state: ReviewState) -> ReviewState:
    """综合评级节点 - 按 4 维度结果给出 PASS/RISK/FAIL。

    Input: state.authority_result, state.procedure_result, state.content_result
    Output: state.risk_result + state.overall_status
    Prompt: prompts.risk_assessment.v1.0.0
    Eval: 与人工标注 kappa ≥ 0.85
    Harness: Quality（必须有 4 维度评分理由）
    """
    import json

    variables = {
        "authority_result": json.dumps(
            state.get("authority_result").model_dump() if state.get("authority_result") else {},
            ensure_ascii=False,
        ),
        "procedure_result": json.dumps(
            state.get("procedure_result").model_dump() if state.get("procedure_result") else {},
            ensure_ascii=False,
        ),
        "content_result": json.dumps(
            state.get("content_result").model_dump() if state.get("content_result") else {},
            ensure_ascii=False,
        ),
    }

    raw, output = await _run_llm_node(
        state,
        prompt_key="risk_assessment",
        variables=variables,
        agent_name="risk_assessment",
        next_node="evidence_verify",
    )

    # 写入 overall_status
    overall = raw.get("overall_status")
    if overall in ("pass", "risk", "fail"):
        state["overall_status"] = overall  # type: ignore[assignment]

    state["risk_result"] = output
    return state


# ============== evidence_verify 节点 ==============
async def evidence_verify_node(state: ReviewState) -> ReviewState:
    """证据校验节点 - 触发 Retry Loop。

    Input: 全部 AgentOutput（authority/procedure/content/risk）
    Output: state.verify_result
    Prompt: prompts.evidence_verify.v1.0.0
    Eval: 证据覆盖率 100%
    Harness: Quality（核心节点）+ Evidence（强制证据校验）；触发 Retry Loop

    Sprint 4 强校验：
    - LLM 判断 + EvidenceHarness.enforce_silent 双重校验
    - 任一 *_result 缺失证据字段 → node_status=RETRY（触发 Router Retry Edge）
    - 全部通过 + LLM PASS → node_status=PASS（路由到 report_generation）
    """
    import json

    from app.agent.harness import EvidenceHarness

    # 合并 4 个 Agent 的输出
    authority = state.get("authority_result")
    procedure = state.get("procedure_result")
    content = state.get("content_result")
    risk = state.get("risk_result")
    all_results = {
        "authority": authority.model_dump() if authority else None,
        "procedure": procedure.model_dump() if procedure else None,
        "content": content.model_dump() if content else None,
        "risk": risk.model_dump() if risk else None,
    }
    legal_context = state.get("legal_context") or []
    variables = {
        "all_results": json.dumps(all_results, ensure_ascii=False),
        "legal_context": _format_legal_context(legal_context),
    }

    raw, output = await _run_llm_node(
        state,
        prompt_key="evidence_verify",
        variables=variables,
        agent_name="evidence_verify",
        # 实际下一节点由 evidence_verify_router 决定
        # PASS→report_generation / RETRY→legal_retrieve / 超限→human_fallback
        next_node="report_generation",
        task_status=TaskStatus.VERIFYING,
    )

    # === Sprint 4 强校验：EvidenceHarness.enforce_silent 双重把关 ===
    # 对每个 *_result（authority/procedure/content/risk）单独校验
    harness_missing: dict[str, list[str]] = {}
    for key, result in (
        ("authority", state.get("authority_result")),
        ("procedure", state.get("procedure_result")),
        ("content", state.get("content_result")),
        ("risk", state.get("risk_result")),
    ):
        if result is None:
            continue
        _, missing = EvidenceHarness.enforce_silent(result)
        if missing:
            harness_missing[key] = missing

    if harness_missing:
        # 任一缺失证据 → 强制 RETRY（覆盖 LLM 的 PASS 判断，触发 Router Retry Edge）
        logger.warning(
            "evidence_harness_missing",
            task_id=state["task_id"],
            trace_id=state["trace_id"],
            missing=harness_missing,
        )
        output.node_status = NodeStatus.RETRY
        output.raw_json["harness_missing"] = harness_missing
        # 路由表：evidence_verify RETRY → legal_retrieve（重新检索法规补证据）
        output.raw_json["next_node"] = "legal_retrieve"
    else:
        # 全部通过：信任 LLM 的 node_status 判断（PASS/RETRY）
        output.raw_json["harness_missing"] = {}
        output.raw_json["next_node"] = (
            "report_generation" if output.node_status == NodeStatus.PASS else "legal_retrieve"
        )

    state["verify_result"] = output
    return state


# ============== report_generation 节点 ==============
async def report_generation_node(state: ReviewState) -> ReviewState:
    """报告生成节点 - 结构化审查报告。

    Input: 全部 AgentOutput, overall_status, user_context
    Output: state.report_result（含 report_markdown）
    Prompt: prompts.report_generation.v1.0.0
    Eval: 报告完整性 100%，引用回链率 100%
    Harness: Evidence（章节"审查依据"必须列出全部引用法规）
    """
    import json

    doc_json = state.get("document_json") or {}
    all_evidences: list[dict[str, Any]] = []

    # 收集全部 evidences
    for key in ("authority_result", "procedure_result", "content_result", "risk_result"):
        result = state.get(key)
        if result is None:
            continue
        for ev in result.evidences:
            all_evidences.append({
                "law_name": ev.law_name,
                "article": ev.article,
                "original_text": ev.original_text,
            })

    variables = {
        "doc_info": json.dumps({
            "title": doc_json.get("title", ""),
            "issuing_authority": doc_json.get("issuing_authority", ""),
            "publish_date": doc_json.get("publish_date", ""),
            "doc_number": doc_json.get("doc_number", ""),
        }, ensure_ascii=False),
        "overall_status": state.get("overall_status", "pass"),
        "authority_result": json.dumps(
            state.get("authority_result").model_dump() if state.get("authority_result") else {},
            ensure_ascii=False,
        ),
        "procedure_result": json.dumps(
            state.get("procedure_result").model_dump() if state.get("procedure_result") else {},
            ensure_ascii=False,
        ),
        "content_result": json.dumps(
            state.get("content_result").model_dump() if state.get("content_result") else {},
            ensure_ascii=False,
        ),
        "risk_result": json.dumps(
            state.get("risk_result").model_dump() if state.get("risk_result") else {},
            ensure_ascii=False,
        ),
        "all_evidences": json.dumps(all_evidences, ensure_ascii=False),
    }

    raw, output = await _run_llm_node(
        state,
        prompt_key="report_generation",
        variables=variables,
        agent_name="report_generation",
        next_node="human_review",
        task_status=TaskStatus.REPORTING,
        max_tokens=8192,  # 报告长文，避免 4096 截断
    )

    state["report_result"] = output
    return state


# ============== human_review 节点 ==============
async def human_review_node(state: ReviewState) -> ReviewState:
    """人工复核节点 - 等待人工确认/反馈。

    Input: state.report_result
    Output: state.feedback, state.finished
    Harness: 人工审查闭环（不可省）
    """
    task_id = state["task_id"]
    trace_id = state["trace_id"]
    bind_trace_id(trace_id)

    # 更新任务状态为 human_review
    async with get_session_factory()() as db:
        task_result = await db.execute(
            select(ReviewTask).where(ReviewTask.id == UUID(task_id))
        )
        task = task_result.scalar_one_or_none()
        if task is not None:
            task.current_node = "human_review"
            task.status = TaskStatus.HUMAN_REVIEW
            await db.commit()

    state["needs_human_review"] = True
    logger.info(
        "human_review_pending",
        task_id=task_id,
        trace_id=trace_id,
    )

    # Sprint 6 实现：等待人工通过 API 提交 feedback
    # Sprint 4 stub：直接标记为完成（测试用）
    return state


# ============== human_fallback 节点 ==============
async def human_fallback_node(state: ReviewState) -> ReviewState:
    """人工兜底节点 - 证据校验超限时触发。

    Input: state.verify_result（FAIL）
    Output: 转 human_review
    Harness: Agent 循环有上限（硬约束触发）
    """
    task_id = state["task_id"]
    trace_id = state["trace_id"]
    bind_trace_id(trace_id)

    logger.warning(
        "human_fallback_triggered",
        task_id=task_id,
        trace_id=trace_id,
        iteration=state.get("iteration", 0),
        max_iteration=state.get("max_iteration", 5),
    )

    # 更新任务状态
    async with get_session_factory()() as db:
        task_result = await db.execute(
            select(ReviewTask).where(ReviewTask.id == UUID(task_id))
        )
        task = task_result.scalar_one_or_none()
        if task is not None:
            task.current_node = "human_fallback"
            task.status = TaskStatus.HUMAN_REVIEW
            await db.commit()

    state["needs_human_review"] = True
    state["error"] = "evidence_verify 超限，转人工兜底"
    return state


# ============== 后台任务触发器（FastAPI BackgroundTask 调用） ==============
async def trigger_doc_parse_background(*, task_id: UUID, document_id: UUID) -> None:
    """触发完整 LangGraph 审查工作流（端到端联调入口）。

    工作流链路（build_review_graph）：
    doc_parse → doc_classify → legal_retrieve → authority_review →
    procedure_review → content_review → risk_assessment →
    evidence_verify → report_generation → human_review → END

    异常隔离：工作流失败不影响上传 API 响应（已 201 返回），
    失败时更新 task 状态为 FAILED。

    UI-M8：使用 astream(stream_mode="updates") 流式触发，
    每节点 enter 通知（node_running）由 notifier 单独会话写入，
    节点运行期间异常被隔离，不影响后续节点与最终状态。
    """
    logger.info(
        "trigger_review_workflow",
        task_id=str(task_id),
        document_id=str(document_id),
    )
    from app.agent.graph import build_review_graph
    from app.agent.state import new_state
    from app.services.notifier import emit_node_done, emit_node_running

    state = new_state(task_id=str(task_id), trace_id=str(task_id))

    # 1. 取 recipient_id（任务提交人 = 通知接收人）
    recipient_id: UUID | None = None
    try:
        async with get_session_factory()() as db:
            t = (
                await db.execute(
                    select(ReviewTask).where(ReviewTask.id == task_id)
                )
            ).scalar_one_or_none()
            if t is not None:
                recipient_id = t.submitter_id
    except Exception as e:
        logger.warning("trigger_load_recipient_failed", error=str(e))

    # 2. 启动图流；每收一个节点 chunk 触发 node_running 与 node_done 通知
    completed_nodes: set[str] = set()
    try:
        graph = build_review_graph()
        async for chunk in graph.astream(state, stream_mode="updates"):
            # chunk: dict[str, dict] - {node_name: state_update}
            for node_name in chunk.keys():
                if not isinstance(node_name, str) or node_name in completed_nodes:
                    continue
                if recipient_id is None:
                    continue
                try:
                    async with get_session_factory()() as ndb:
                        await emit_node_running(
                            ndb,
                            recipient_id=recipient_id,
                            task_id=task_id,
                            node_name=node_name,
                            iteration=state.get("iteration", 0),
                        )
                except Exception as e:
                    logger.warning(
                        "trigger_notify_running_failed",
                        node=node_name,
                        error=str(e),
                    )

            # 一个节点 chunk 出现 = 该节点已执行完一次更新
            for node_name in chunk.keys():
                if not isinstance(node_name, str) or node_name in completed_nodes:
                    continue
                completed_nodes.add(node_name)
                if recipient_id is None:
                    continue
                try:
                    async with get_session_factory()() as ndb:
                        await emit_node_done(
                            ndb,
                            recipient_id=recipient_id,
                            task_id=task_id,
                            node_name=node_name,
                            iteration=state.get("iteration", 0),
                        )
                except Exception as e:
                    logger.warning(
                        "trigger_notify_done_failed",
                        node=node_name,
                        error=str(e),
                    )
        logger.info(
            "review_workflow_done",
            task_id=str(task_id),
            nodes_completed=sorted(completed_nodes),
        )
    except Exception as e:
        logger.error(
            "review_workflow_exception",
            task_id=str(task_id),
            error=str(e),
        )
        # 更新任务状态为失败（便于前端感知）
        try:
            async with get_session_factory()() as db:
                task_result = await db.execute(
                    select(ReviewTask).where(ReviewTask.id == task_id)
                )
                task = task_result.scalar_one_or_none()
                if task:
                    task.status = TaskStatus.FAILED
                    task.current_node = "error"
                    await db.commit()
        except Exception:
            pass
