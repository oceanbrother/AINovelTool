# -*- coding: utf-8 -*-
"""Unit tests for embedding.py — LRU cache logic.

The cache is the non-model part of the embedding layer: deterministic, fast,
and separately testable without SentenceTransformer or torch.
"""
import pytest
from app.core.embedding import _cache_get, _cache_put, _CACHE_MAX


class TestLRUCache:
    def setup_method(self):
        """Clear the module-level cache before each test."""
        from app.core import embedding
        embedding._cache.clear()

    def teardown_method(self):
        from app.core import embedding
        embedding._cache.clear()

    def test_cache_miss(self):
        assert _cache_get("never seen") is None

    def test_cache_hit(self):
        _cache_put("key", [0.1, 0.2, 0.3])
        result = _cache_get("key")
        assert result == [0.1, 0.2, 0.3]

    def test_cache_overwrite(self):
        _cache_put("key", [1.0])
        _cache_put("key", [2.0])
        assert _cache_get("key") == [2.0]

    def test_lru_eviction(self):
        """When cache exceeds _CACHE_MAX, the least recently used entry is evicted."""
        # Fill cache to max+1
        for i in range(_CACHE_MAX + 10):
            _cache_put(str(i), [float(i)])
        # The earliest entries should be gone
        assert _cache_get("0") is None  # evicted
        assert _cache_get("1") is None  # evicted
        # Latest entries still present
        assert _cache_get(str(_CACHE_MAX + 9)) == [float(_CACHE_MAX + 9)]

    def test_get_refreshes_position(self):
        """A cache hit moves the entry to the end (most-recently-used)."""
        from app.core import embedding
        embedding._cache.clear()
        # Put exactly two entries — "a" is LRU, "b" is MRU
        _cache_put("a", [1.0])
        _cache_put("b", [2.0])
        assert len(embedding._cache) == 2
        # Access "a" to make it MRU — now "b" is LRU
        assert _cache_get("a") == [1.0]
        # Verify "a" is now last (MRU), "b" is first (LRU)
        keys = list(embedding._cache.keys())
        assert keys[0] == "b"  # LRU
        assert keys[-1] == "a"  # MRU

    def test_cache_max_is_reasonable(self):
        """Sanity check: cache should hold at least 100 entries."""
        assert _CACHE_MAX >= 100


class TestEmbedTexts:
    """Test the public API with the local backend (requires sentence-transformers).

    These are integration-level tests — skip if torch is not installed.
    """
    @pytest.mark.asyncio
    async def test_empty_input(self):
        from app.core.embedding import embed_texts
        assert await embed_texts([]) == []

    @pytest.mark.asyncio
    async def test_single_text(self):
        pytest.importorskip("sentence_transformers")
        from app.core.embedding import embed_texts
        vectors = await embed_texts(["测试文本"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 1024  # bge-m3 dim

    @pytest.mark.asyncio
    async def test_multiple_texts(self):
        pytest.importorskip("sentence_transformers")
        from app.core.embedding import embed_texts
        texts = ["第一段", "第二段", "第三段"]
        vectors = await embed_texts(texts)
        assert len(vectors) == 3

    @pytest.mark.asyncio
    async def test_cache_returns_same_vector(self):
        pytest.importorskip("sentence_transformers")
        from app.core.embedding import embed_texts, _cache_get
        texts = ["缓存测试文本"]
        v1 = await embed_texts(texts)
        # Second call should hit cache
        v2 = await embed_texts(texts)
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_embed_text_convenience(self):
        pytest.importorskip("sentence_transformers")
        from app.core.embedding import embed_text
        vec = await embed_text("单条文本")
        assert len(vec) == 1024
