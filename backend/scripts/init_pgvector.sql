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
    source_label TEXT,               -- style provenance: epub / manual / 内化
    scene_tag   TEXT,                -- style scene: 战斗/对话/日常/景物/心理
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
-- Narrative units and plans — structure the prose can be pointed at
-- ---------------------------------------------------------------------------
-- A chapter is one long blob, so nothing could refer to "the scene where he
-- finds the note": no ordering, no setup/payoff edges, nowhere to attach a
-- label. narrative_units supplies that handle. Chapters are NOT mirrored as
-- rows here — scenes reference their chapter, and parent_id waits for beats.
--
-- narrative_plans fixes the more expensive loss: a ScenePlan used to be
-- generated, edited, sent to the writer and dropped, discarding every decision
-- the author made. Without it nothing can be locked against regeneration, no
-- per-scene record exists for long-form metrics, and function labels have
-- nowhere to live. The plan is JSONB because its shape is still moving and it
-- is only ever fetched whole.

CREATE TABLE IF NOT EXISTS narrative_units (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter_id      BIGINT REFERENCES chapters(id) ON DELETE CASCADE,
    parent_id       BIGINT REFERENCES narrative_units(id) ON DELETE CASCADE,
    level           TEXT NOT NULL DEFAULT 'scene',   -- room for 'beat' later
    order_index     INTEGER NOT NULL DEFAULT 0,      -- order within the chapter
    text            TEXT NOT NULL DEFAULT '',
    surface_summary TEXT,                            -- what happened, plainly
    scene_tag       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_narrative_units_order
    ON narrative_units(project_id, chapter_id, order_index);

CREATE TABLE IF NOT EXISTS narrative_plans (
    id                BIGSERIAL PRIMARY KEY,
    project_id        BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter_id        BIGINT REFERENCES chapters(id) ON DELETE SET NULL,
    unit_id           BIGINT REFERENCES narrative_units(id) ON DELETE SET NULL,
    fragment          TEXT,                          -- what it was planned from
    plan              JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- ScenePlan field names the author froze; these survive regeneration
    locked_fields     JSONB NOT NULL DEFAULT '[]'::jsonb,
    review_status     TEXT NOT NULL DEFAULT 'pending',   -- pending/approved/rejected
    generation_status TEXT NOT NULL DEFAULT 'planned',   -- planned/written/accepted
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_narrative_plans_project
    ON narrative_plans(project_id, chapter_id);

-- ---------------------------------------------------------------------------
-- Story facts — who currently knows what
-- ---------------------------------------------------------------------------
-- The reader's awareness is deliberately separate from every character's: that
-- gap is suspense. A reader who knows what the protagonist does not is dramatic
-- irony, and a single "revealed yet?" flag (what foreshadowing.status is) cannot
-- express it. Character awareness sits in JSONB keyed by character id — the row
-- count is small, the shape matches characters.persona, and a fact's whole state
-- stays readable in one row. Only characters the author registers appear there;
-- absence means "not modelled", not "ignorant".

CREATE TABLE IF NOT EXISTS story_facts (
    id               BIGSERIAL PRIMARY KEY,
    project_id       BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    statement        TEXT NOT NULL,             -- stated plainly; quoted verbatim
                                                -- into the constraints derived from it
    is_true          BOOLEAN NOT NULL DEFAULT TRUE,  -- false = a lie or red herring
    reader_level     TEXT NOT NULL DEFAULT 'unknown',
    -- {"<character_id>": "unknown|suspects|knows|believes_false"}
    character_levels JSONB NOT NULL DEFAULT '{}'::jsonb,
    foreshadowing_id BIGINT REFERENCES foreshadowing(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_story_facts_project ON story_facts(project_id);

-- When someone's awareness of a fact changed. story_facts holds what is known
-- NOW, which stops a character saying what they cannot know but cannot answer
-- "had the reader met this before chapter N?" — the question narrative-function
-- labelling turned out to require. A level is resolved as the most recent event
-- at or before the chapter in question; with no events the columns on
-- story_facts still apply, so existing rows keep working untouched.
-- Author-controlled on purpose: deciding when something may be known is the
-- most consequential pacing power in a long work, and a model will spend it
-- early because a resolved scene feels complete.

CREATE TABLE IF NOT EXISTS knowledge_events (
    id          BIGSERIAL PRIMARY KEY,
    project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    fact_id     BIGINT NOT NULL REFERENCES story_facts(id) ON DELETE CASCADE,
    holder_type TEXT NOT NULL,          -- 'reader' | 'character'
    holder_id   BIGINT,                 -- characters.id, for 'character' only
    level       TEXT NOT NULL,          -- unknown/suspects/knows/believes_false
    chapter_id  BIGINT REFERENCES chapters(id) ON DELETE CASCADE,  -- NULL = 开篇起
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_knowledge_events_fact
    ON knowledge_events(project_id, fact_id);

-- ---------------------------------------------------------------------------
-- Author overrides — (what the tool suggested, what the author kept)
-- ---------------------------------------------------------------------------
-- Every rewrite before a merge is behavioural evidence about the author's own
-- voice, which beats asking them to describe it. The pair only exists because
-- the draft box is editable BEFORE merging; once text lands in the chapter the
-- edits blend in and the pairing is unrecoverable.
-- Texture deltas are stored on write (services/rhythm.texture, pure + zero LLM).
-- These numbers must never be injected into a generation prompt — that was
-- tested and measurably hurt output; they are for post-hoc selection and for
-- surfacing the author's own accepted prose as examples.

CREATE TABLE IF NOT EXISTS style_overrides (
    id                 BIGSERIAL PRIMARY KEY,
    project_id         BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter_id         BIGINT,
    source             TEXT NOT NULL,        -- continue / imitate / refine
    suggested_text     TEXT NOT NULL,
    accepted_text      TEXT NOT NULL,
    edit_ratio         REAL NOT NULL DEFAULT 0,  -- 0 = verbatim, 1 = rewritten
    -- accepted − suggested; the sign is the preference
    d_dialogue_ratio   REAL,
    d_short_sent_ratio REAL,
    d_avg_sent_len     REAL,
    d_punct_density    REAL,
    d_avg_para_len     REAL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_style_overrides_project
    ON style_overrides(project_id, source);

-- ---------------------------------------------------------------------------
-- Rhythm analysis — ordered reference corpus (local-only private data)
-- ---------------------------------------------------------------------------
-- Decoupled from setting_chunks on purpose: that table serves retrieval and is
-- evenly sampled + deduped, which destroys the adjacency rhythm analysis needs.
-- Here segments are contiguous and ordered by (work, chapter_no, seq). No
-- embedding column — sequence statistics don't need vectors.
-- Corpus prose stays on this machine; only aggregate statistics ever leave it.

CREATE TABLE IF NOT EXISTS corpus_segments (
    id               BIGSERIAL PRIMARY KEY,
    work             TEXT NOT NULL,
    chapter_no       INTEGER NOT NULL,    -- spine order, 1-based
    chapter_title    TEXT,
    seq              INTEGER NOT NULL,    -- order within the chapter, 1-based
    text             TEXT NOT NULL,
    char_len         INTEGER NOT NULL,
    -- texture layer: computed by services/rhythm.py, deterministic, zero LLM
    dialogue_ratio   REAL,
    short_sent_ratio REAL,
    avg_sent_len     REAL,
    punct_density    REAL,
    avg_para_len     REAL,
    -- tag layer: two independent labellers kept apart so they can be compared
    scene_tag_anchor TEXT,                -- anchor-vector classifier
    scene_tag_llm    TEXT,                -- judge model
    func_tag         TEXT,                -- 转折 / 揭示 / 承接 / 铺垫
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_corpus_segments_order
    ON corpus_segments(work, chapter_no, seq);

-- Paragraphs — the unit rhythm is actually measured in. A ~450-char segment
-- spans ~8 paragraphs and so contains every rendering mode at once (54% of them
-- mixed dialogue with narration), which hides the very alternation rhythm is
-- made of. Paragraphs (~64 chars) usually hold a single mode.
-- Three label columns stay separate so labellers can be checked against each
-- other: a quotation-mark rule, the local anchor classifier, and the judge model.
CREATE TABLE IF NOT EXISTS corpus_paragraphs (
    id          BIGSERIAL PRIMARY KEY,
    work        TEXT NOT NULL,
    chapter_no  INTEGER NOT NULL,
    seq         INTEGER NOT NULL,     -- order within the chapter, 1-based
    segment_id  BIGINT,               -- parent scene beat in corpus_segments
    text        TEXT NOT NULL,
    char_len    INTEGER NOT NULL,
    is_dialogue BOOLEAN,              -- quotation-mark rule (free, near-certain)
    mode_rule   TEXT,                 -- 对话 when the rule fires
    mode_anchor TEXT,                 -- 对话/动作/描写/心理/叙述 via services/mode.py
    mode_llm    TEXT,                 -- same vocabulary, judge model
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_corpus_paragraphs_order
    ON corpus_paragraphs(work, chapter_no, seq);

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

-- 作者对生成提示词的覆盖。只存覆盖，默认值留在 app/services/ 的源码里——
-- 这样新库能直接跑，升级改了默认值也不会静默盖掉作者编辑过的内容。
--
-- 这里刻意不收三条量具（约束核对 / 风格评分 / 功能标注）。本项目记录的每一个
-- 数字（约束兑现 59%→93%、kappa 0.310、两阶段 88.0% vs 72.6%）都是用那几个
-- 字符串测出来的，让它们漂移会让新旧数字不可比，而且无从察觉。这道锁是结构性
-- 的：verify_draft / judge_draft / 标注器都不接收 DB session，没有任何代码路径
-- 能读到覆盖值。
CREATE TABLE IF NOT EXISTS prompt_templates (
    id          BIGSERIAL PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,          -- services/prompts.py 里声明的槽位
    body        TEXT NOT NULL,
    revision    INTEGER NOT NULL DEFAULT 1,    -- 每次保存 +1
    based_on    TEXT,                          -- 这次编辑分叉自哪个默认值；升级后用于提示"基线已过时"
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
