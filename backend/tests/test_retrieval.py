# -*- coding: utf-8 -*-
"""Unit tests for retrieval.py — channel matrix configuration.

The channel matrix is the central routing table: every feature reads through a
named channel, and the channel decides which sources may answer. A typo in a
channel name is a KeyError rather than silently returning wrong results.
"""
import pytest
from app.services.retrieval import CHANNELS


class TestChannelMatrix:
    def test_known_channels_exist(self):
        """Every channel used in the codebase must be defined."""
        assert "hints" in CHANNELS
        assert "generate" in CHANNELS
        assert "style" in CHANNELS
        assert "debug" in CHANNELS

    def test_debug_channel_is_unfiltered(self):
        """The debug channel must see all sources — it's the truth reference."""
        assert CHANNELS["debug"] is None

    def test_style_channel_is_style_only(self):
        """The style channel must not return fact settings."""
        assert CHANNELS["style"] == ["style"]

    def test_hints_and_generate_have_same_sources(self):
        """Both fact channels draw from the same pool."""
        assert CHANNELS["hints"] == CHANNELS["generate"]

    def test_channel_values_are_lists_or_none(self):
        for name, sources in CHANNELS.items():
            assert sources is None or isinstance(sources, list), (
                f"Channel '{name}' must be list or None, got {type(sources)}"
            )

    def test_source_types_are_strings(self):
        for name, sources in CHANNELS.items():
            if sources is not None:
                for s in sources:
                    assert isinstance(s, str), (
                        f"Source type in channel '{name}' must be str"
                    )

    def test_no_duplicate_sources_in_channel(self):
        for name, sources in CHANNELS.items():
            if sources is not None:
                assert len(sources) == len(set(sources)), (
                    f"Channel '{name}' has duplicate source types"
                )

    def test_channel_keyerror_for_unknown(self):
        """An unknown channel name raises KeyError — fail fast, not silently."""
        with pytest.raises(KeyError):
            _ = CHANNELS["nonexistent_channel"]
