import pytest
from unittest.mock import patch, MagicMock
from src.brain.dedup import deduplicate_pairs


def test_dedup_removes_near_duplicates():
    pairs = [
        {"messages": [{"role": "assistant", "content": "I led Kafka governance for 5 teams."}], "metadata": {}},
        {"messages": [{"role": "assistant", "content": "I led Kafka governance for five teams."}], "metadata": {}},
        {"messages": [{"role": "assistant", "content": "I optimized SQL queries reducing latency by 93%."}], "metadata": {}},
    ]
    # Mock embeddings: first two are near-duplicates (high similarity), third is unique
    import numpy as np
    fake_embeddings = np.array([
        [1.0, 0.0, 0.0],   # pair 0
        [0.95, 0.05, 0.0], # pair 1 - similar to pair 0 (cosine ~0.95)
        [0.0, 0.0, 1.0],   # pair 2 - unique
    ])
    with patch("src.brain.dedup._get_embeddings", return_value=fake_embeddings):
        result = deduplicate_pairs(pairs, threshold=0.90)
    assert len(result) == 2  # First two are near-duplicates


def test_dedup_keeps_unique():
    pairs = [
        {"messages": [{"role": "assistant", "content": "I led Kafka governance."}], "metadata": {}},
        {"messages": [{"role": "assistant", "content": "I optimized SQL queries."}], "metadata": {}},
        {"messages": [{"role": "assistant", "content": "I migrated auth to OAuth2."}], "metadata": {}},
    ]
    import numpy as np
    fake_embeddings = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    with patch("src.brain.dedup._get_embeddings", return_value=fake_embeddings):
        result = deduplicate_pairs(pairs, threshold=0.92)
    assert len(result) == 3


def test_dedup_empty_list():
    assert deduplicate_pairs([], threshold=0.92) == []


def test_embeddings_model_loaded_once(monkeypatch):
    import src.brain.dedup as d
    calls = []

    class _FakeST:
        def __init__(self, name):
            calls.append(name)

        def encode(self, texts, **kw):
            import numpy as np
            return np.ones((len(texts), 8))

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", _FakeST)
    # setattr (not bare assignment): monkeypatch restores the pre-test value on
    # teardown, so the fake model instance set inside _get_embeddings never
    # leaks into later tests via the d._EMBED_MODEL singleton.
    monkeypatch.setattr(d, "_EMBED_MODEL", None, raising=False)
    d._get_embeddings(["a", "b"])
    d._get_embeddings(["c"])
    assert len(calls) == 1
