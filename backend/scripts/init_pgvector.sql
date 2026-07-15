-- =============================================================================
-- AI Novel Assistant — PostgreSQL + pgvector schema
-- =============================================================================
-- This single database holds BOTH relational data (projects / characters /
-- chapters ...) AND vector data (setting_chunks / literary_knowledge / idioms).
-- Keeping them together lets us JOIN structured filters with vector search in
-- one query — no separate vector DB to keep in sync.
--
-- Embedding dimension is fixed at the column level. Default = 1024 (bge-m3).
-- If you switch to bge-small-zh-v1.5 (512 dims), change every `vector(1024)`
-- below to `vector(512)` and re-run, then re-embed all chunks.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Core narrative tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS projects (
    id          BIGSERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT,
    genre       TEXT DEFAULT '都市幻想',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS characters (
    id          BIGSERIAL PRIMARY KEY,
    project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    -- persona holds structured traits: {"性格": ..., "能力": ..., "口癖": ...}
    persona     JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id);

CREATE TABLE IF NOT EXISTS relationships (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    character_a_id  BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    character_b_id  BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    relation_type   TEXT,            -- 师徒 / 宿敌 / 盟友 ...
    description     TEXT
);
CREATE INDEX IF NOT EXISTS idx_relationships_project ON relationships(project_id);

CREATE TABLE IF NOT EXISTS world_settings (
    id          BIGSERIAL PRIMARY KEY,
    project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category    TEXT NOT NULL,       -- 规则 / 势力 / 地点
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_world_project ON world_settings(project_id);

CREATE TABLE IF NOT EXISTS chapters (
    id          BIGSERIAL PRIMARY KEY,
    project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL DEFAULT 0,
    title       TEXT,
    content     TEXT NOT NULL DEFAULT '',
    summary     TEXT,                -- per-chapter abstract (for rolling summary)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chapters_project_order ON chapters(project_id, order_index);

CREATE TABLE IF NOT EXISTS foreshadowing (
    id                BIGSERIAL PRIMARY KEY,
    project_id        BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title             TEXT NOT NULL,
    content           TEXT,
    status            TEXT NOT NULL DEFAULT 'open',   -- open / closed
    setup_chapter_id  BIGINT REFERENCES chapters(id) ON DELETE SET NULL,
    payoff_chapter_id BIGINT REFERENCES chapters(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_foreshadowing_project ON foreshadowing(project_id);

CREATE TABLE IF NOT EXISTS rolling_summary (
    id                BIGSERIAL PRIMARY KEY,
    project_id        BIGINT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    content           TEXT NOT NULL DEFAULT '',
    up_to_chapter_id  BIGINT REFERENCES chapters(id) ON DELETE SET NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Vector / retrieval tables
-- ---------------------------------------------------------------------------

-- Unified, retrievable chunks of project setting material.
-- source_type tells us where a chunk came from so we can filter by category
-- (角色 / 世界观 / 伏笔 / 文风) before or alongside the vector search.
CREATE TABLE IF NOT EXISTS setting_chunks (
    id          BIGSERIAL PRIMARY KEY,
    project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,       -- character / world / foreshadowing / style
    source_id   BIGINT,              -- id in the originating table (nullable)
    content     TEXT NOT NULL,
    embedding   vector(1024),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_setting_chunks_project ON setting_chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_setting_chunks_source  ON setting_chunks(source_type, source_id);
-- HNSW: high recall, no training step required. Cosine distance.
CREATE INDEX IF NOT EXISTS idx_setting_chunks_embed
    ON setting_chunks USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- v1.1 — Literary citation library (public-domain works only)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS literary_works (
    id               BIGSERIAL PRIMARY KEY,
    title            TEXT NOT NULL,
    author           TEXT NOT NULL,
    era              TEXT,                       -- 年代 / 时期
    -- 体裁/主题分类：诗歌 / 戏剧 / 散文 / 志怪文学，小说按主题细分为
    -- 爱情文学 / 战争文学 / 现实文学 / 哲学 / 成长文学
    category         TEXT,
    is_public_domain BOOLEAN NOT NULL DEFAULT TRUE,
    themes           JSONB NOT NULL DEFAULT '[]'::jsonb,  -- 主题标签数组
    school           TEXT,                       -- 流派
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Retrievable literary knowledge: author background / theme reading /
-- recognized famous lines / criticism. Embedded for semantic search.
CREATE TABLE IF NOT EXISTS literary_knowledge (
    id             BIGSERIAL PRIMARY KEY,
    work_id        BIGINT REFERENCES literary_works(id) ON DELETE CASCADE,
    knowledge_type TEXT NOT NULL,    -- 作者背景 / 主题解读 / 公认名句 / 句式
    content        TEXT NOT NULL,
    embedding      vector(1024),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lit_knowledge_work ON literary_knowledge(work_id);
CREATE INDEX IF NOT EXISTS idx_lit_knowledge_embed
    ON literary_knowledge USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- v1.1 — Idiom library (public asset; retrieval-grounded, anti-hallucination)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS idioms (
    id            BIGSERIAL PRIMARY KEY,
    text          TEXT NOT NULL UNIQUE,
    meaning       TEXT NOT NULL,
    tags          JSONB NOT NULL DEFAULT '[]'::jsonb,   -- 语义标签
    usage_context TEXT,                                  -- 适用语境
    embedding     vector(1024),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_idioms_embed
    ON idioms USING hnsw (embedding vector_cosine_ops);
