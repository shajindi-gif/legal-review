"""RAG 混合检索服务 - 关键词 trigram + HNSW 向量 + 元数据过滤。

来自 02_SYSTEM_ARCHITECTURE.md + 04_AGENT_GRAPH_DESIGN.md 3.3 节。

检索流程：
1. query → embedding（同 BGE-M3）
2. 向量召回：pgvector HNSW ANN，余弦距离
3. 关键词召回：pg_trgm 全文相似度
4. 归一化分数 + 加权融合（vector_weight / keyword_weight）
5. 元数据过滤：law_type / law_level / law_status
6. 时效过滤：默认仅 effective
7. Top-K 返回，含完整证据链字段

性能：
- HNSW ef_search=40（可调）
- trgm similarity_threshold=0.1（法律文本通常较长）
- 单次检索 P95 ≤ 200ms 目标
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AgentError
from app.core.logging import get_logger
from app.schemas.legal import RAGSearchRequest, RAGSearchResponse, RAGSearchResultItem
from app.tools.embedding import get_embedding_provider

logger = get_logger("tools.rag")


# 混合检索 SQL（向量 + trgm + 元数据过滤 + RRF 融合）
# 注意：pgvector 的 <=> 是余弦距离，越小越相似；转为相似度 1 - distance
_HYBRID_SEARCH_SQL = """
WITH vec AS (
    SELECT
        c.id AS clause_id,
        c.law_id,
        c.chapter,
        c.section,
        c.article_no,
        c.article_title,
        c.content,
        c.keywords,
        (c.embedding <=> :emb) AS vector_distance
    FROM legal_clauses c
    JOIN legal_documents d ON c.law_id = d.id
    WHERE d.deleted_at IS NULL
      AND d.status = ANY(COALESCE(:law_statuses, ARRAY['effective']::text[]))
      AND (CAST(:law_types AS text[]) IS NULL OR d.law_type = ANY(CAST(:law_types AS text[])))
      AND (CAST(:law_levels AS text[]) IS NULL OR d.law_level = ANY(CAST(:law_levels AS text[])))
      AND c.embedding IS NOT NULL
    ORDER BY c.embedding <=> :emb
    LIMIT :k_vec
),
kw AS (
    SELECT
        c.id AS clause_id,
        c.law_id,
        c.chapter,
        c.section,
        c.article_no,
        c.article_title,
        c.content,
        c.keywords,
        similarity(c.content, :query) AS kw_sim
    FROM legal_clauses c
    JOIN legal_documents d ON c.law_id = d.id
    WHERE d.deleted_at IS NULL
      AND d.status = ANY(COALESCE(:law_statuses, ARRAY['effective']::text[]))
      AND (CAST(:law_types AS text[]) IS NULL OR d.law_type = ANY(CAST(:law_types AS text[])))
      AND (CAST(:law_levels AS text[]) IS NULL OR d.law_level = ANY(CAST(:law_levels AS text[])))
      AND c.content % :query
    ORDER BY kw_sim DESC
    LIMIT :k_kw
)
SELECT
    COALESCE(v.clause_id, k.clause_id) AS clause_id,
    COALESCE(v.law_id, k.law_id) AS law_id,
    COALESCE(v.chapter, k.chapter) AS chapter,
    COALESCE(v.section, k.section) AS section,
    COALESCE(v.article_no, k.article_no) AS article_no,
    COALESCE(v.article_title, k.article_title) AS article_title,
    COALESCE(v.content, k.content) AS content,
    COALESCE(v.keywords, k.keywords, ARRAY[]::varchar[]) AS keywords,
    d.law_name,
    d.law_type,
    d.law_level,
    d.status AS law_status,
    d.publish_date,
    -- 归一化分数（0~1）
    CASE WHEN v.vector_distance IS NOT NULL
         THEN 1.0 - v.vector_distance ELSE 0.0 END AS vector_score,
    COALESCE(k.kw_sim, 0.0) AS keyword_score,
    -- 加权融合
    (:vector_weight * (CASE WHEN v.vector_distance IS NOT NULL
                            THEN 1.0 - v.vector_distance ELSE 0.0 END)
     + :keyword_weight * COALESCE(k.kw_sim, 0.0)) AS final_score
FROM vec v
FULL OUTER JOIN kw k ON v.clause_id = k.clause_id
JOIN legal_documents d ON COALESCE(v.law_id, k.law_id) = d.id
ORDER BY final_score DESC
LIMIT :top_k
"""


class RAGSearchService:
    """RAG 混合检索。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, req: RAGSearchRequest) -> RAGSearchResponse:
        """混合检索。"""
        start = time.monotonic()

        # 1. query → embedding
        provider = get_embedding_provider()
        try:
            query_emb = await provider.embed(req.query)
        except AgentError:
            raise
        except Exception as e:
            raise AgentError("legal_retrieve", f"query embedding 失败: {e}") from e

        # 2. 混合检索 SQL
        params: dict[str, Any] = {
            "emb": str(query_emb),  # pgvector 接受 list 或 string
            "query": req.query,
            "law_types": [t.value if hasattr(t, "value") else t for t in req.law_types]
            if req.law_types
            else None,
            "law_levels": [
                lv.value if hasattr(lv, "value") else lv for lv in req.law_levels
            ]
            if req.law_levels
            else None,
            "law_statuses": [s.value if hasattr(s, "value") else s for s in req.law_status]
            if req.law_status
            else None,
            "vector_weight": req.vector_weight,
            "keyword_weight": req.keyword_weight,
            "k_vec": max(req.top_k * 3, 30),  # 召回扩大 3 倍再融合
            "k_kw": max(req.top_k * 3, 30),
            "top_k": req.top_k,
        }

        result = await self._session.execute(text(_HYBRID_SEARCH_SQL), params)
        rows = result.all()

        items: list[RAGSearchResultItem] = []
        for row in rows:
            items.append(
                RAGSearchResultItem(
                    clause_id=row.clause_id,
                    law_id=row.law_id,
                    law_name=row.law_name,
                    law_type=row.law_type,
                    law_level=row.law_level,
                    law_status=row.law_status,
                    publish_date=row.publish_date,
                    chapter=row.chapter,
                    section=row.section,
                    article_no=row.article_no,
                    article_title=row.article_title,
                    content=row.content,
                    keywords=row.keywords or [],
                    vector_score=round(float(row.vector_score), 4),
                    keyword_score=round(float(row.keyword_score), 4),
                    final_score=round(float(row.final_score), 4),
                )
            )

        took_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "rag_search_done",
            query=req.query[:80],
            total=len(items),
            took_ms=took_ms,
            provider=provider.name,
        )
        return RAGSearchResponse(
            query=req.query,
            total=len(items),
            items=items,
            took_ms=took_ms,
        )

    async def search_simple(
        self,
        query: str,
        *,
        top_k: int = 10,
        law_status: list[str] | None = None,
    ) -> list[RAGSearchResultItem]:
        """简化版检索（默认参数）。"""
        req = RAGSearchRequest(
            query=query,
            top_k=top_k,
            law_status=law_status,  # type: ignore[arg-type]
        )
        resp = await self.search(req)
        return resp.items
