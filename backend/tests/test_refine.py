# -*- coding: utf-8 -*-
"""Unit tests for refine.py — parser, cosine, and settings block.

Tests the pure-function parts of the agentic loop:
  * _parse_json — the gate that caught the silent-zero-constraint bug
  * _cosine — dot product for L2-normalised vectors
  * _settings_block — prompt assembly helper
  * program_checks — the checklist that verifies must_include/must_not
"""
import pytest
from app.services.refine import (
    PlanParseError,
    _cosine,
    _parse_json,
    _settings_block,
    MAX_DIRECT_EMOTION,
    REPETITION_THRESHOLD,
)


class TestParseJson:
    def test_valid_json(self):
        result = _parse_json('{"goal": "test", "must_include": ["a"]}')
        assert result == {"goal": "test", "must_include": ["a"]}

    def test_json_with_markdown_fence(self):
        """JSON inside markdown code fences — common LLM output."""
        raw = '```json\n{"goal": "test"}\n```'
        result = _parse_json(raw)
        assert result == {"goal": "test"}

    def test_json_with_surrounding_text(self):
        """LLM often wraps JSON in explanatory text."""
        raw = '这是一个计划：\n{"goal": "完成场景"}\n以上是计划内容。'
        result = _parse_json(raw)
        assert result == {"goal": "完成场景"}

    def test_empty_string_raises(self):
        with pytest.raises(PlanParseError, match="empty"):
            _parse_json("")

    def test_whitespace_only_raises(self):
        with pytest.raises(PlanParseError, match="empty"):
            _parse_json("   \n  ")

    def test_no_braces_raises(self):
        with pytest.raises(PlanParseError, match="no JSON object"):
            _parse_json("这是一段没有JSON的纯文本。")

    def test_invalid_json_raises(self):
        with pytest.raises(PlanParseError, match="not valid JSON"):
            _parse_json('{"goal": "test", broken}')

    def test_nested_braces(self):
        """Only the outermost braces are matched."""
        raw = '{"outer": {"inner": 1}}'
        result = _parse_json(raw)
        assert result == {"outer": {"inner": 1}}

    def test_realistic_plan_output(self):
        raw = (
            '好的，以下是场景计划：\n\n'
            '{\n'
            '  "goal": "暴露主角的心理缺口",\n'
            '  "must_include": ["幻想被选中", "用琐碎现实打断"],\n'
            '  "must_not": ["确认超自然存在"],\n'
            '  "end_state": "主角仍然被动"\n'
            '}'
        )
        result = _parse_json(raw)
        assert result["goal"] == "暴露主角的心理缺口"
        assert len(result["must_include"]) == 2


class TestCosine:
    def test_identical_vectors(self):
        v = [0.5, 0.5, 0.5, 0.5]
        # Dot product of L2-normalised vectors
        norm = sum(x**2 for x in v) ** 0.5
        v_norm = [x / norm for x in v]
        assert _cosine(v_norm, v_norm) == pytest.approx(1.0)

    def test_orthogonal(self):
        assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite(self):
        assert _cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_empty_vectors(self):
        assert _cosine([], []) == 0.0


class TestSettingsBlock:
    def test_empty_chunks(self):
        result = _settings_block([])
        assert "无命中" in result

    def test_with_chunks(self):
        class FakeChunk:
            def __init__(self, source_type, content):
                self.source_type = source_type
                self.content = content

        chunks = [
            FakeChunk("character", "主角是一个孤独的少年。"),
            FakeChunk("world", "夜幕协定禁止在凡人面前使用力量。"),
        ]
        result = _settings_block(chunks)
        assert "[设定0]" in result
        assert "character" in result
        assert "主角是一个孤独的少年" in result
        assert "[设定1]" in result

    def test_with_cap(self):
        class FakeChunk:
            def __init__(self, content):
                self.source_type = "world"
                self.content = content

        long_text = "很长的设定文本。" * 50
        chunks = [FakeChunk(long_text)]
        result = _settings_block(chunks, cap=50)
        assert "…" in result
        assert len(result) < len(long_text) + 100

    def test_no_cap(self):
        class FakeChunk:
            def __init__(self, content):
                self.source_type = "world"
                self.content = content

        text = "短设定"
        chunks = [FakeChunk(text)]
        result = _settings_block(chunks)  # cap=0 means no cap
        assert text in result


class TestConstants:
    def test_max_direct_emotion_is_positive(self):
        assert MAX_DIRECT_EMOTION > 0

    def test_repetition_threshold_in_range(self):
        assert 0.0 < REPETITION_THRESHOLD < 1.0
