"""Deterministic offline LLM provider for the portfolio demo and CI.

Routes on prompt markers and scores by skill-keyword overlap so the
pipeline behaves plausibly with zero API keys. Every route returns
non-empty text (LLMGateway failover skips empty strings).
"""
import json
import re
from typing import Optional

from src.core.gateway.base import BaseLLMProvider
from src.core.persona import SAMPLE_SKILLS

_STACK = [s.lower() for s in SAMPLE_SKILLS]
_GHOST_TELLS = [
    "rockstar", "ninja", "many openings", "multiple openings",
    "immediate start", "reposted", "salary range tbd",
]


class MockLLMProvider(BaseLLMProvider):
    """Offline stand-in for a real LLM. Deterministic; safe for demos/CI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(api_key=api_key or "mock", model=model or "mock-1", base_url=base_url)

    def is_available(self) -> bool:
        return True

    def _overlap(self, text: str) -> int:
        low = text.lower()
        return sum(1 for k in _STACK if k in low)

    def generate(
        self,
        prompt: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        low = prompt.lower()

        if "block_a" in low or "7-block" in low:
            score = min(95, 40 + 7 * self._overlap(prompt))
            ghost = any(t in low for t in _GHOST_TELLS)
            if ghost:
                score = min(score, 45)
            blocks = {
                f"block_{c}": {"score": round(score / 100 * 10), "notes": "mock evaluation"}
                for c in "abcdefg"
            }
            blocks["block_g"]["is_ghost_job"] = ghost
            return json.dumps({
                "fit_score": score,
                "reason": "Mock evaluation: keyword-overlap heuristic.",
                **blocks,
            })

        if "worth_applying" in low:
            score = min(95, 40 + 7 * self._overlap(prompt))
            return json.dumps({
                "score": score,
                "worth_applying": score >= 72,
                "reason": "Mock scoring: skill overlap.",
                "title": "Mock title",
                "stack": "Python, FastAPI",
                "location_remote": "US / Remote",
            })

        if "optimized_bullets" in low or "target company:" in low:
            company = "the company"
            m = re.search(r"Target Company:\s*(.+)", prompt)
            if m:
                company = m.group(1).strip()
            return json.dumps({
                "summary": (
                    f"Backend engineer targeting {company}: high-throughput "
                    f"pipelines, measurable p95 wins, platform ownership."
                ),
                "optimized_bullets": [
                    "Built event-ingestion platform (Python, FastAPI, Kafka) at 40M events/day, cutting p95 latency 62%.",
                    "Led ECS-to-Kubernetes migration for 14 services with zero-downtime cutover in 6 weeks.",
                    "Reworked payment capture with idempotency keys, eliminating duplicate charges.",
                ],
                "role_2_bullets": [
                    "Sharded orders database by merchant_id, reducing p99 query time 71%.",
                    "Built webhook delivery system with 99.97% on-time delivery.",
                ],
            })

        if "cover letter" in low:
            return (
                "Dear Hiring Team,\n\nI am Alex Rivera, a backend engineer whose "
                "work on high-throughput event pipelines and platform migrations "
                "maps closely to this role.\n\nBest regards,\nAlex Rivera"
            )

        if "interview" in low or "star" in low:
            return (
                "Situation: ingestion lag during traffic spike. Task: restore "
                "real-time processing. Action: backpressure batching + autoscaling "
                "on consumer lag. Result: lag cleared in 18 minutes, no data loss."
            )

        return "Mock response: deterministic offline provider for demo purposes."
