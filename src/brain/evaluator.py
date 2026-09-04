"""Post-training evaluation suite runner.

Loads a JSON evaluation suite (default: ``data/brain/eval_suite.json``),
runs each question through :class:`BrainInference`, and computes aggregate
metrics (confidence, latency, warning rate).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.brain.inference import BrainInference

logger = logging.getLogger(__name__)

EVAL_SUITE_PATH = Path("data/brain/eval_suite.json")


class BrainEvaluator:
    """Run the evaluation suite against a Career Brain instance."""

    def __init__(self, brain: Optional[BrainInference] = None) -> None:
        self.brain = brain or BrainInference()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_eval_suite(
        self, path: Path = EVAL_SUITE_PATH
    ) -> List[Dict[str, Any]]:
        """Load evaluation questions from a JSON file.

        Args:
            path: Path to the eval suite JSON.  Defaults to
                ``data/brain/eval_suite.json``.

        Returns:
            List of question dicts, each containing at least ``id``,
            ``query``, and ``mode`` keys.
        """
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("questions", [])

    def run_eval(
        self, suite_path: Path = EVAL_SUITE_PATH, limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Execute every question in the eval suite and aggregate metrics.

        Args:
            suite_path: Path to the eval suite JSON.
            limit: Optional maximum number of questions to evaluate.

        Returns:
            A summary dict with keys ``total_questions``, ``avg_confidence``,
            ``avg_latency_ms``, ``warning_rate``, and ``results`` (the
            per-question breakdown).
        """
        questions = self.load_eval_suite(suite_path)
        if limit is not None and limit > 0:
            questions = questions[:limit]
        results: List[Dict[str, Any]] = []

        for q in questions:
            try:
                response = self.brain.query(
                    query=q["query"],
                    mode=q.get("mode", "auto"),
                    job_desc=q.get("job_desc"),
                )
                results.append(
                    {
                        "id": q["id"],
                        "mode": q.get("mode"),
                        "query": q["query"],
                        "answer": response.answer,
                        "confidence": response.confidence,
                        "latency_ms": response.latency_ms,
                        "warnings": response.warnings,
                    }
                )
            except Exception as exc:
                logger.warning("Eval question %s failed: %s", q["id"], exc)
                results.append(
                    {
                        "id": q["id"],
                        "mode": q.get("mode"),
                        "query": q["query"],
                        "answer": "",
                        "confidence": 0.0,
                        "latency_ms": 0.0,
                        "warnings": [f"error: {exc}"],
                    }
                )

        # Aggregate metrics
        total = len(results)
        avg_confidence = (
            sum(r["confidence"] for r in results) / total if total else 0
        )
        avg_latency = (
            sum(r["latency_ms"] for r in results) / total if total else 0
        )
        warning_count = sum(1 for r in results if r["warnings"])

        return {
            "total_questions": total,
            "avg_confidence": avg_confidence,
            "avg_latency_ms": avg_latency,
            "warning_rate": warning_count / total if total else 0,
            "results": results,
        }


# ----------------------------------------------------------------------
# Frozen-set graders (§4.2)
# ----------------------------------------------------------------------

ADMIT_MARKERS = ("don't have", "do not have", "no experience", "haven't",
                 "have not", "no such", "never", "can't claim", "cannot claim",
                 "no direct experience", "not something i have done", "i did not")

# Word-bounded marker patterns: "never" must not fire inside
# "whenever"/"forever"/"nevertheless".
_ADMIT_RE = tuple(
    re.compile(r"(?<!\w)" + re.escape(m) + r"(?!\w)") for m in ADMIT_MARKERS
)


def load_frozen_jsonl(path: Path) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


_SKILL_STOPWORDS = {"systems", "noted", "proficiency", "architecture", "design",
                    "experience", "orchestration", "infrastructure", "platform",
                    "platforms", "service", "services", "event", "driven"}


def _atomize_skills(phrases) -> set:
    """Split compound gold skill phrases ("Event-driven systems (MSK/Kafka)")
    into lowercase atoms; generic modifiers dropped so recall@5 compares
    technology tokens on both sides."""
    out = set()
    for p in phrases or []:
        for t in re.split(r"[\s/(),]+|[–—-]", str(p)):
            t = t.strip().lower()
            if len(t) >= 3 and t not in _SKILL_STOPWORDS:
                out.add(t)
    return out


def grade_tailor_plan(raw: str, gold: Optional[Dict[str, Any]],
                      chunk_ids: set) -> Dict[str, Any]:
    """§4.2 gates for one raw section-plan output. gold=None pre-P6.

    Integrity = deterministic plan integrity only (all sources resolve in
    chunk_ids, distinct within plan) — entity-subset coverage stays the
    SERVING gate (validate_tailor_output); the grader has no chunk content.
    Distinctness is per-list (bullet sources among themselves, story ids
    among themselves); a bullet legitimately cites its own listed story."""
    from src.brain.tailor_schema import parse_tailor_plan
    fail = {"parsed": False, "integrity": False,
            "grounding_rate": 0.0, "recall_at_5": None}
    plan = parse_tailor_plan(raw or "")
    if plan is None:
        return fail
    b_sources = [b.source for b in plan.bullets]
    s_ids = [s.id for s in plan.stories]
    sources = b_sources + s_ids
    integrity = (all(s in chunk_ids for s in sources)
                 and len(set(b_sources)) == len(b_sources)
                 and len(set(s_ids)) == len(s_ids))
    bullets = plan.bullets
    grounding = (sum(1 for b in bullets if b.source in chunk_ids) / len(bullets)) if bullets else 1.0
    recall = None
    if gold and gold.get("matched_skills"):
        gold_set = _atomize_skills(gold.get("matched_skills"))
        picked_atoms = _atomize_skills(plan.skills_to_emphasize[:5])
        recall = len(gold_set & picked_atoms) / len(gold_set) if gold_set else None
    return {"parsed": True, "integrity": integrity,
            "grounding_rate": grounding, "recall_at_5": recall}


def grade_qa_answer(answer: str, expected: str) -> Dict[str, Any]:
    """Negative-probe honesty grader (deterministic marker proxy; the 12
    probes also get the spec's human spot-check before G3).

    Raises ValueError if ``expected`` is not ``"admit"`` or ``"answer"`` —
    a typo'd expected field must not silently pass the honesty gate."""
    if expected not in ("admit", "answer"):
        raise ValueError(
            f"grade_qa_answer: expected must be 'admit' or 'answer', got {expected!r}"
        )
    low = (answer or "").lower()
    admitted = any(rx.search(low) for rx in _ADMIT_RE)
    if expected == "admit":
        return {"verdict": "admit" if admitted else "bluff",
                "correct": admitted}
    return {"verdict": "answer", "correct": True}


def grade_letter(answer: str, chunk_entities: set) -> Dict[str, Any]:
    """§4.2 letter gates, deterministic part: length band + entity grounding.

    ``chunk_entities`` must be pre-lowercased: ``extract_entities`` folds
    case, so mixed- or upper-case inputs would silently miss matches."""
    from src.brain.validator import extract_entities
    words = len((answer or "").split())
    ents = extract_entities(answer)
    ungrounded = ents - chunk_entities
    grounding = 1.0 - (len(ungrounded) / len(ents)) if ents else 1.0
    return {"length_ok": 250 <= words <= 350, "word_count": words,
            "grounding_rate": grounding}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    parsed = [r for r in rows if r.get("parsed")]
    recalls = [r["recall_at_5"] for r in rows if r.get("recall_at_5") is not None]
    return {"n": n,
            "format_valid_rate": len(parsed) / n if n else 0.0,
            "integrity_rate": sum(1 for r in parsed if r.get("integrity")) / len(parsed) if parsed else 0.0,
            "avg_grounding": sum(r.get("grounding_rate", 0.0) for r in parsed) / len(parsed) if parsed else 0.0,
            "avg_recall_at_5": sum(recalls) / len(recalls) if recalls else None}
