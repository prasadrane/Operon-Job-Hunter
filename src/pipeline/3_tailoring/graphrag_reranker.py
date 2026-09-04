"""FlashRank ONNX INT8 reranker for STAR subgraph clusters with MMR diversity.

Provides:
- GraphRAGReranker: cross-encoder reranker using FlashRank (CPU-only, <15MB INT8 ONNX)
- STARCluster: dataclass for STAR narrative cluster metadata
- MMR (Maximal Marginal Relevance) for diversity-aware selection
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from flashrank import Ranker, RerankRequest


@dataclass(frozen=True)
class STARCluster:
    """Structured STAR narrative cluster.

    Fields:
        role: Candidate role/title in the narrative
        challenge: Problem or situation faced
        action: Specific action taken
        metric: Quantified outcome/metric
    """
    role: str
    challenge: str
    action: str
    metric: str


class GraphRAGReranker:
    """Cross-encoder reranker using FlashRank ONNX INT8 (CPU-only).

    Uses ms-marco-MiniLM-L-6-v2 model by default (~23MB FP32, INT8 quantized ~6MB).
    Falls back to ms-marco-TinyBERT-L-2-v2 (~4MB) if MiniLM unavailable.
    """

    def __init__(self, model_path: str = "ms-marco-MiniLM-L-6-v2") -> None:
        """Initialize reranker with specified model.

        Args:
            model_path: HuggingFace model name or local path. Default ms-marco-MiniLM-L-6-v2.
        """
        try:
            self._ranker = Ranker(model_name=model_path, log_level="ERROR")
        except Exception:
            # Fallback to smaller model if requested model unavailable
            self._ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2", log_level="ERROR")

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 10,
    ) -> list[dict]:
        """Rerank candidates by relevance to query using cross-encoder.

        Args:
            query: Search query text
            candidates: List of candidate dicts with 'text' and 'id' fields
            top_k: Number of top results to return

        Returns:
            Reranked candidates sorted by relevance_score descending,
            with 'relevance_score' field added. Returns [] for empty input.
        """
        if not candidates:
            return []

        # Build passages for FlashRank
        passages = []
        for c in candidates:
            text = c.get("text", "")
            pid = c.get("id", "")
            passages.append({"id": pid, "text": text})

        # Run cross-encoder reranking
        request = RerankRequest(query=query, passages=passages)
        ranked = self._ranker.rerank(request)

        # Build score lookup from ranked results
        score_map: dict[str, float] = {}
        for item in ranked:
            score_map[str(item.get("id", ""))] = float(item.get("score", 0.0))

        # Attach scores and sort descending
        scored = []
        for c in candidates:
            entry = dict(c)
            entry["relevance_score"] = score_map.get(c.get("id", ""), 0.0)
            scored.append(entry)

        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored[:top_k]

    def compute_mmr(
        self,
        candidates: list[dict],
        lambda_param: float = 0.7,
    ) -> list[dict]:
        """Apply Maximal Marginal Relevance for diversity-aware selection.

        MMR balances relevance (score) vs diversity (dissimilarity to already-selected).
        Formula: MMR(d) = λ * score(d) - (1-λ) * max_sim(d, selected)

        Hard constraint: no two candidates from the same cluster. Once a cluster
        is represented in the selected set, all other candidates from that cluster
        are excluded from consideration.

        Args:
            candidates: List of candidate dicts with 'relevance_score' and 'cluster' fields
            lambda_param: Trade-off parameter. 0.0 = pure relevance, 1.0 = pure diversity.

        Returns:
            Candidates reordered by MMR score, with 'relevance_score' preserved.
            No two candidates share the same cluster.
        """
        if not candidates:
            return []

        # Ensure scores exist
        for c in candidates:
            if "relevance_score" not in c:
                c["relevance_score"] = 0.0

        selected: list[dict] = []
        selected_clusters: set[str] = set()
        remaining = list(candidates)

        while remaining:
            best = None
            best_mmr = -math.inf

            for cand in remaining:
                cluster = cand.get("cluster", "")

                # Hard constraint: skip if cluster already selected
                if cluster and cluster in selected_clusters:
                    continue

                # Relevance term
                rel = cand["relevance_score"]

                # Diversity term: max similarity to any selected candidate
                if not selected:
                    max_sim = 0.0
                else:
                    max_sim = max(
                        1.0 if s.get("cluster", "") == cluster else 0.0
                        for s in selected
                    )

                # MMR score
                mmr_score = lambda_param * rel - (1.0 - lambda_param) * max_sim

                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best = cand

            if best is None:
                # All remaining candidates are from already-selected clusters
                # or no valid candidate found; stop
                break

            selected.append(best)
            cluster = best.get("cluster", "")
            if cluster:
                selected_clusters.add(cluster)
            remaining.remove(best)

        return selected
