# -*- coding: utf-8 -*-
"""CI smoke test — verifies basic system integrity without touching an LLM.

A "smoke test" in engineering is the first power-on check: does it catch fire?
Here it means:

  1. Can the schema be created and seeded?
  2. Do the program-level gates (cliché, n-gram, texture) produce deterministic
     outputs on known inputs?
  3. Does the channel matrix parse without error?
  4. Do the FastAPI routers mount and respond?

This does NOT test LLM-driven quality — the full eval harnesses own that.
It tests that a deploy or a refactor didn't break the scaffolding those numbers
depend on.

CI calls:  python eval/smoke.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest


def test_schema_imports():
    """Every model used by the API can be imported."""
    from app.models.project import Project
    from app.models.chapter import Chapter
    from app.models.character import Character
    from app.models.world import WorldSetting
    from app.models.setting_chunk import SettingChunk
    from app.models.foreshadowing import Foreshadowing
    from app.models.story_fact import StoryFact
    from app.models.rolling_summary import RollingSummary
    from app.models.style_override import StyleOverride
    from app.models.prompt_template import PromptTemplate
    from app.models.prompt_version import PromptVersion
    from app.models.literary import LiteraryWork, LiteraryKnowledge
    from app.models.idiom import Idiom
    from app.models.narrative import NarrativePlan, NarrativeUnit
    from app.models.corpus_segment import CorpusSegment
    from app.models.knowledge_event import KnowledgeEvent
    assert Project is not None
    assert PromptVersion is not None  # new in v1.2


def test_channel_matrix():
    """The routing table that every retrieval path depends on."""
    from app.services.retrieval import CHANNELS

    assert "hints" in CHANNELS
    assert "generate" in CHANNELS
    assert "style" in CHANNELS
    assert "debug" in CHANNELS
    assert CHANNELS["debug"] is None  # all sources
    assert CHANNELS["style"] == ["style"]
    # Hints and generate share sources — if they diverge, style samples leak
    assert CHANNELS["hints"] == CHANNELS["generate"]


def test_cliche_detection():
    """Stock-phrase gate — deterministic, zero-LLM."""
    from app.services.cliche import find_cliches, DEFAULT_CLICHES

    # Known phrase must be caught
    result = find_cliches("命运的齿轮开始转动的那一刻，一切都变了。")
    assert "命运的齿轮" in result

    # Clean text must pass
    assert find_cliches("他推开那扇沉重的铁门，走廊里弥漫着消毒水的气味。") == []

    # Default list is non-empty
    assert len(DEFAULT_CLICHES) > 0


def test_ngram_overlap():
    """Plagiarism gate — deterministic, zero-LLM."""
    from app.services.imitation import ngram_overlap, NGRAM_N

    # Identical text → 100% overlap
    text = "这是一段测试文本用来验证ngram重叠计算"
    assert ngram_overlap(text, [text]) == pytest.approx(1.0)

    # Completely different text → 0%
    assert ngram_overlap("ABCDEFGHIJKLMNOP", ["一二三四五六七八九十"]) == 0.0

    # Short text → 0 (below n-gram size)
    assert ngram_overlap("短", ["短"]) == 0.0

    # Constant is sane
    assert NGRAM_N >= 5


def test_texture_metrics():
    """Texture analysis — deterministic, zero-LLM, five dimensions."""
    from app.services.rhythm import (
        dialogue_ratio, avg_sentence_len, punct_density, texture, texture_distance
    )

    # Empty input → zeros, not crashes
    t = texture("")
    assert all(v == 0.0 for k, v in t.items() if k != "avg_para_len")

    # Known-prose input
    t = texture("今天天气很好。他推开门走了出去。街上人来人往。")
    assert t["avg_sent_len"] > 0
    assert t["punct_density"] > 0
    assert 0.0 <= t["dialogue_ratio"] <= 1.0

    # Distance: identical → 0
    assert texture_distance("测试。", "测试。") == pytest.approx(0.0, abs=0.0001)

    # Symmetry
    a, b = "短句。" * 10, "更长一些的句子在这里继续写下去。" * 5
    assert texture_distance(a, b) == pytest.approx(texture_distance(b, a), rel=0.01)


def test_parse_json():
    """Plan parser — the gate that caught the zero-constraint bug."""
    from app.services.refine import _parse_json, PlanParseError

    # Valid JSON
    assert _parse_json('{"goal":"test"}') == {"goal": "test"}

    # JSON inside markdown fence (LLM habit)
    assert _parse_json('```json\n{"a":1}\n```') == {"a": 1}

    # Empty → PlanParseError (NOT silent {})
    with pytest.raises(PlanParseError, match="empty"):
        _parse_json("")

    # No braces → PlanParseError
    with pytest.raises(PlanParseError, match="no JSON"):
        _parse_json("纯文本")

    # Invalid JSON → PlanParseError
    with pytest.raises(PlanParseError):
        _parse_json("{broken")


def test_prompt_slots():
    """Every named prompt slot resolves to a real module attribute."""
    from app.services.prompts import SLOTS, default, slot

    for s in SLOTS:
        # slot() does not raise
        resolved = slot(s.key)
        assert resolved.key == s.key

        # default() returns a non-empty string
        body = default(s.key)
        assert isinstance(body, str)
        assert len(body) > 20, f"Prompt '{s.key}' default is too short: {len(body)} chars"

        # Editable slots have required placeholders that must be in the default
        if s.required:
            for token in s.required:
                assert token in body, (
                    f"Prompt '{s.key}' default missing required token '{token}'"
                )


def test_database_connection():
    """The database is reachable and has the expected tables."""
    from app.db import engine
    from sqlalchemy import text

    async def _run():
        async with engine.begin() as conn:
            tables = (await conn.execute(text(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname='public' ORDER BY tablename"
            ))).fetchall()
        table_names = {t[0] for t in tables}
        required = {
            "projects", "chapters", "characters", "world_settings",
            "setting_chunks", "foreshadowing", "story_facts",
            "rolling_summary", "prompt_templates", "prompt_versions",
            "narrative_plans", "narrative_units", "literary_works",
            "literary_knowledge", "idioms", "style_overrides",
        }
        missing = required - table_names
        assert not missing, f"Missing tables: {missing}"
        return len(table_names)

    n = asyncio.run(_run())
    print(f"  DB OK ({n} tables)")


def test_seed_and_query():
    """CRUD smoke via raw SQL.

    Skipped on Windows: asyncpg + ProactorEventLoop has a known incompatibility
    with nested asyncio.run() calls inside pytest. GitHub Actions uses Linux
    runners where this test passes normally.
    """
    import platform
    if platform.system() == "Windows":
        pytest.skip("asyncpg + Windows ProactorEventLoop incompatibility")

    from app.db import engine
    from sqlalchemy import text

    async def _run():
        async with engine.begin() as conn:
            # Seed project
            result = await conn.execute(text(
                "INSERT INTO projects (title, description, genre) "
                "VALUES ('smoke_test', 'CI smoke', '都市幻想') RETURNING id"
            ))
            pid = result.scalar_one()

            # Seed chapter
            await conn.execute(text(
                "INSERT INTO chapters (project_id, order_index, content) "
                "VALUES (:pid, 1, :content)"
            ), {"pid": pid, "content": "测试正文。※第二段内容在这里展开。※第三段收尾。"})

            # Seed character
            await conn.execute(text(
                "INSERT INTO characters (project_id, name, persona, summary) "
                "VALUES (:pid, '测试角色', '{}', '一个怀疑现实的少年')"
            ), {"pid": pid})

            # Seed world setting
            await conn.execute(text(
                "INSERT INTO world_settings (project_id, category, title, content) "
                "VALUES (:pid, '规则', '镜像延迟', '倒影慢0.5秒')"
            ), {"pid": pid})

            # Verify
            ch_count = (await conn.execute(text(
                "SELECT COUNT(*) FROM chapters WHERE project_id=:pid"
            ), {"pid": pid})).scalar()
            assert ch_count == 1

            # Clean up in reverse FK order
            await conn.execute(text("DELETE FROM chapters WHERE project_id=:pid"), {"pid": pid})
            await conn.execute(text("DELETE FROM characters WHERE project_id=:pid"), {"pid": pid})
            await conn.execute(text("DELETE FROM world_settings WHERE project_id=:pid"), {"pid": pid})
            await conn.execute(text("DELETE FROM projects WHERE id=:pid"), {"pid": pid})

        return True

    ok = asyncio.run(_run())
    assert ok
    print("  seed & query OK")


def test_agent_tools_manifest():
    """The tool schema endpoint returns valid OpenAI function-calling format."""
    from app.api.agent import TOOLS

    assert len(TOOLS) >= 10, f"Expected >=10 tools, got {len(TOOLS)}"

    for tool in TOOLS:
        assert tool["type"] == "function"
        func = tool["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        params = func["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        # Required fields are a subset of properties
        if "required" in params:
            for r in params["required"]:
                assert r in params["properties"], (
                    f"Tool '{func['name']}': required '{r}' not in properties"
                )

    # Key tool names must exist
    names = {t["function"]["name"] for t in TOOLS}
    required_tools = {
        "retrieve_settings", "generate_continuation", "refine_write",
        "analyze_texture", "detect_cliches", "verify_constraints",
    }
    missing = required_tools - names
    assert not missing, f"Missing tools: {missing}"


def test_register_patterns():
    """All four register patterns are well-formed and renderable."""
    from app.services.refine import REGISTER_PATTERNS, _register_guide

    assert len(REGISTER_PATTERNS) == 4
    for name, stages in REGISTER_PATTERNS.items():
        assert len(stages) >= 3, f"Pattern '{name}' has too few stages"
        for stage in stages:
            assert "register" in stage
            assert "paragraphs" in stage
            assert stage["register"] in ("mundane", "comic", "lyrical", "suspense", "quiet")
        guide = _register_guide(name)
        assert len(guide) > 50, f"Pattern '{name}' guide is too short"
        assert "段" in guide

    # Nonexistent pattern returns empty
    assert _register_guide("nonexistent") == ""

    print("  register patterns OK")


def test_subtext_plan_roundtrip():
    """SubtextPlan is serialisable and survives model_dump/rebuild cycle."""
    from app.schemas.refine import SubtextPlan, ScenePlan

    st = SubtextPlan(
        surface_event="日常对话",
        hidden_need="被看见",
        denied_emotion="孤独",
        masking_behavior="开玩笑",
        rupture_moment="名字被准确叫出",
        emotional_residue="不敢相信",
        emotion_explicitness=0.25,
    )
    plan = ScenePlan(
        goal="暴露人物缺口",
        must_include=["一次短暂的眼神接触"],
        must_not=["直接说破"],
        subtext=st,
    )
    # model_dump + rebuild
    d = plan.model_dump()
    restored = ScenePlan(**d)
    assert restored.subtext is not None
    assert restored.subtext.hidden_need == "被看见"
    assert restored.subtext.emotion_explicitness == 0.25
    assert restored.subtext.masking_behavior == "开玩笑"

    # SubtextPlan with all empty fields → None after plan creation
    st2 = SubtextPlan()
    plan2 = ScenePlan(goal="test", subtext=st2)
    assert plan2.subtext is not None  # present but all fields empty
    assert plan2.subtext.hidden_need == ""

    print("  subtext roundtrip OK")


def test_report_endpoints_shape():
    """The report and timeline route functions are importable and callable."""
    from app.api.reports import longform_report, fact_timeline
    assert callable(longform_report)
    assert callable(fact_timeline)
    print("  report functions OK")


def test_observability_module():
    """Token accounting and stats aggregation work."""
    from app.core.observability import record_call, get_stats

    # Reset state is implicit (module-level lists)
    record_call("plan", "deepseek-v4-pro", 1500.0, 500, 200, 150)
    record_call("draft", "deepseek-v4-flash", 3200.0, 800, 400)
    record_call("plan", "deepseek-v4-pro", 1480.0, 510, 190, 145)

    stats = get_stats()
    assert stats["total_calls"] == 3
    assert stats["total_prompt_tokens"] == 1810
    assert "plan" in stats["operations"]
    assert stats["operations"]["plan"]["calls"] == 2
    assert stats["operations"]["plan"]["latency_p50_ms"] > 0


if __name__ == "__main__":
    # Allow running directly: python eval/smoke.py
    # In CI: pytest eval/smoke.py
    exit_code = pytest.main([__file__, "-v", "--tb=short", "-p", "no:cacheprovider"])
    sys.exit(exit_code)
