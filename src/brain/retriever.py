"""Mode-specific retrieval wrapper around existing GraphRAG infrastructure."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.brain.mode_router import BrainMode


@dataclass
class RetrievedChunk:
    """A single retrieved chunk from the career knowledge graph."""

    id: str
    content: str
    score: float
    chunk_type: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


class BrainRetriever:
    """Retrieve relevant chunks based on brain mode.

    Wraps the existing GraphRetriever/HybridGraphRetriever from
    ``src/pipeline/3_tailoring/`` and adapts results into RetrievedChunk
    instances consumed by the prompt builder.
    """

    def __init__(self, graph_retriever=None):
        if graph_retriever is None:
            # Package name starts with a digit -> importlib required
            import importlib
            graph_retriever_mod = importlib.import_module(
                "src.pipeline.3_tailoring.graph_retriever")
            graph_retriever = graph_retriever_mod.GraphRetriever()
        self.graph_retriever = graph_retriever

    def retrieve(
        self,
        query: str,
        mode: BrainMode,
        top_k: int = 3,
        job_desc: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        """Retrieve top-k chunks relevant to the query and mode.

        Args:
            query: User's natural-language question or request.
            mode: Active brain mode (avatar / tailoring / qa).
            top_k: Maximum chunks per retrieval pass.
            job_desc: Optional job description — triggers a second
                retrieval pass in tailoring mode.

        Returns:
            List of RetrievedChunk instances (deduplicated by id).
        """
        if not query.strip():
            return []

        raw_results = self.graph_retriever.retrieve_rrf(query, top_k=top_k)

        chunks = [self._to_chunk(r) for r in raw_results]

        # For tailoring mode, also retrieve based on job description overlap
        if mode == BrainMode.TAILORING and job_desc and job_desc.strip():
            job_results = self.graph_retriever.retrieve_rrf(job_desc, top_k=top_k)
            seen_ids = {c.id for c in chunks}
            for r in job_results:
                chunk = self._to_chunk(r)
                if chunk.id not in seen_ids:
                    chunks.append(chunk)
                    seen_ids.add(chunk.id)

        return chunks[: top_k * 2]

    @staticmethod
    def _to_chunk(raw: dict) -> RetrievedChunk:
        """Convert a raw retrieval result dict to a RetrievedChunk.

        Handles both GraphRetriever.retrieve_rrf results (node/rrf_score/
        details) and simple dicts (id/content/score) used in tests.
        """
        if isinstance(raw, RetrievedChunk):
            return raw

        # retrieve_rrf shape: {"node", "rrf_score", "type", "details": {...}}
        if "node" in raw:
            details = raw.get("details", {}) or {}
            content = (
                details.get("bullet")
                or "\n".join(details.get("bullets", []))
                or details.get("name")
                or str(raw["node"])
            )
            return RetrievedChunk(
                id=str(raw["node"]),
                content=content,
                score=float(raw.get("rrf_score", 0.0)),
                chunk_type=raw.get("type", "unknown"),
                metadata=details,
            )

        return RetrievedChunk(
            id=raw.get("id", ""),
            content=raw.get("content", ""),
            score=raw.get("score", 0.0),
            chunk_type=raw.get("type", "unknown"),
            metadata=raw.get("metadata", {}),
        )
