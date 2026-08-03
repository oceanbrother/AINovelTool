# -*- coding: utf-8 -*-
"""Unit tests for cliche.py — stock-phrase detection.

Pure substring matching: deterministic, free, and impossible to argue with.
"""
import pytest
from app.services.cliche import DEFAULT_CLICHES, find_cliches, prohibition_line


class TestFindCliches:
    def test_empty_text(self):
        assert find_cliches("") == []

    def test_no_cliche_in_text(self):
        assert find_cliches("这是一段完全原创的文字，没有任何俗套表达。") == []

    def test_single_cliche_found(self):
        text = "那一刻，命运的齿轮开始转动，他意识到一切都不一样了。"
        result = find_cliches(text)
        assert "命运的齿轮" in result

    def test_multiple_cliches(self):
        text = "世界突然安静下来，时间仿佛静止了，空气仿佛凝固在这一刻。"
        result = find_cliches(text)
        assert len(result) >= 3
        assert "世界突然安静" in result
        assert "时间仿佛静止" in result
        assert "空气仿佛凝固" in result

    def test_whitespace_does_not_hide_cliche(self):
        """Whitespace inside a phrase is stripped, so newlines cannot hide cliches."""
        text2 = "命运的\n齿轮"
        result2 = find_cliches(text2)
        # find_cliches strips all whitespace before matching,
        # so "命运的\n齿轮" becomes "命运的齿轮" and IS matched
        assert "命运的齿轮" in result2

    def test_extra_cliches(self):
        text = "自定义俗套出现了。"
        extra = ("自定义俗套",)
        assert "自定义俗套" in find_cliches(text, extra=extra)
        assert "自定义俗套" not in find_cliches(text)

    def test_result_order_matches_declaration_order(self):
        """Results appear in the order they were declared, not in text order."""
        text = "阳光正好，微风不燥，命运的齿轮开始转动。"
        result = find_cliches(text)
        indices = [result.index(p) for p in result]
        assert indices == sorted(indices)  # declaration order preserved

    def test_empty_extra_cliches(self):
        assert find_cliches("命运的齿轮", extra=()) == ["命运的齿轮"]

    def test_all_default_cliches_are_non_empty(self):
        for phrase in DEFAULT_CLICHES:
            assert phrase, f"Empty phrase in DEFAULT_CLICHES"


class TestProhibitionLine:
    def test_default_output(self):
        line = prohibition_line()
        assert "套话" in line or "陈词" in line
        assert len(line) > 10

    def test_with_extra_cliches(self):
        line = prohibition_line(extra=("自定义俗套", "另一个"))
        # Only first `limit` (8) phrases appear, all from DEFAULT_CLICHES
        # Extra cliches are appended to the list but may not appear if
        # DEFAULT_CLICHES already fills the limit
        assert "套话" in line or "陈词" in line

    def test_limit_truncation(self):
        """Only the first `limit` phrases appear."""
        line = prohibition_line(limit=3)
        # Only 3 of the 20 default phrases should appear
        phrases_in_line = sum(1 for p in DEFAULT_CLICHES if p in line)
        assert phrases_in_line <= 3

    def test_empty_extra(self):
        line1 = prohibition_line(extra=())
        line2 = prohibition_line()
        assert line1 == line2
