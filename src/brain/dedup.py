"""Embedding-based deduplication of training pairs."""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np


_EMBED_MODEL = None  # module singleton — one ~80MB model load per process


def _get_embeddings(texts: List[str]) -> np.ndarray:
    """Get embeddings using sentence-transformers."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        from sentence_transformers import SentenceTransformer
        _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _EMBED_MODEL.encode(texts, normalize_embeddings=True)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def deduplicate_pairs(pairs: List[Dict[str, Any]], threshold: float = 0.92) -> List[Dict[str, Any]]:
    """Remove near-duplicate training pairs based on assistant response similarity."""
    if not pairs:
        return []

    # Extract assistant responses
    texts = []
    for pair in pairs:
        assistant_msgs = [m for m in pair.get("messages", []) if m.get("role") == "assistant"]
        texts.append(assistant_msgs[0]["content"] if assistant_msgs else "")

    embeddings = _get_embeddings(texts)
    kept_indices = []

    for i in range(len(pairs)):
        is_duplicate = False
        for j in kept_indices:
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim > threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            kept_indices.append(i)

    return [pairs[i] for i in kept_indices]
