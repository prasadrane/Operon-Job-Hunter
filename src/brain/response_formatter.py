import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks and whitespace from model output."""
    if not text:
        return ""
    # Strip matched <think>...</think> blocks
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text)
    # Strip unclosed leading <think> block if any
    cleaned = re.sub(r"^<think>[\s\S]*", "", cleaned)
    return cleaned.strip()



@dataclass
class Citation:
    """A single citation linking a response claim to a retrieved chunk."""

    chunk_id: str
    relevance: float
    chunk_type: str = "unknown"


@dataclass
class BrainResponse:
    """Structured response from the Career Brain inference pipeline."""

    answer: str
    mode: str
    citations: List[Citation] = field(default_factory=list)
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)
    retrieved_chunks: int = 0
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict suitable for JSON / API responses."""
        return {
            "answer": self.answer,
            "mode": self.mode,
            "citations": [
                {
                    "chunk_id": c.chunk_id,
                    "relevance": c.relevance,
                    "chunk_type": c.chunk_type,
                }
                for c in self.citations
            ],
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "retrieved_chunks": self.retrieved_chunks,
            "latency_ms": self.latency_ms,
        }
