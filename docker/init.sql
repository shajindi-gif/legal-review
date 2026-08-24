-- 初始化扩展：pgvector（向量检索）+ pg_trgm（模糊检索）+ uuid-ossp
-- 三个扩展是 RAG 混合检索（HNSW + trigram + RRF）的前置依赖

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 验证扩展安装
DO $$
BEGIN
    RAISE NOTICE '扩展安装完成: vector + pg_trgm + uuid-ossp';
END $$;
