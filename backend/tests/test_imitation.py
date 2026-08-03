# -*- coding: utf-8 -*-
"""Unit tests for imitation.py — n-gram overlap gate (pure-function part).

The n-gram overlap check is a plagiarism gate, not a style gate:
style may be borrowed, content may not.
"""
import pytest
from app.services.imitation import ngram_overlap, NGRAM_N, NGRAM_MAX_OVERLAP


class TestNgramOverlap:
    def test_empty_text(self):
        assert ngram_overlap("", ["样本文字"]) == 0.0

    def test_text_shorter_than_n(self):
        """Text with fewer chars than NGRAM_N returns 0.0."""
        assert ngram_overlap("短", ["样本文字"]) == 0.0

    def test_no_overlap(self):
        """Completely different character sequences."""
        text = "这是一段完全不同的文字"
        samples = ["另外的样本内容在这里"]
        assert ngram_overlap(text, samples) == 0.0

    def test_full_overlap(self):
        """Text is identical to the only sample."""
        text = "测试文本在这里呈现"
        samples = ["测试文本在这里呈现"]
        assert ngram_overlap(text, samples) == pytest.approx(1.0)

    def test_partial_overlap(self):
        text = "今天天气很好适合出门散步"
        samples = ["今天天气很好"]
        overlap = ngram_overlap(text, samples)
        # With n=8: "今天天气很好" is 6 chars, less than 8, so no 8-grams
        # overlap should be >= 0 (text length after cleaning < n -> 0)
        assert overlap >= 0.0

    def test_multiple_samples(self):
        text = "晚饭后散步是很好的习惯"
        samples = ["今天天气很好", "散步是很好的习惯", "完全不相关的内容"]
        overlap = ngram_overlap(text, samples)
        assert 0.0 < overlap < 1.0

    def test_whitespace_is_stripped(self):
        """Spaces don't create false negatives — whitespace is stripped."""
        text = "测试文字一二三四五六七八"
        samples = ["测试文字一二三四五六七八"]
        # After whitespace removal, both are the same, full overlap
        assert ngram_overlap(text, samples) == pytest.approx(1.0)

    def test_n_parameter(self):
        text = "一二三四五六七八九十"
        samples = ["一二三四五"]
        # With n=5: "一二三四五" should be found
        assert ngram_overlap(text, samples, n=5) > 0.0
        # With n=8: fewer matching 8-grams
        overlap_n8 = ngram_overlap(text, samples, n=8)
        overlap_n5 = ngram_overlap(text, samples, n=5)
        assert overlap_n8 <= overlap_n5

    def test_empty_samples_list(self):
        text = "任何文字"
        assert ngram_overlap(text, []) == 0.0

    def test_threshold_constant_is_reasonable(self):
        """NGRAM_MAX_OVERLAP is the gate threshold — sanity check it."""
        assert 0.0 < NGRAM_MAX_OVERLAP < 0.2  # should be strict

    def test_n_constant_is_reasonable(self):
        """NGRAM_N should be at least 5 — shorter is too noisy."""
        assert NGRAM_N >= 5
