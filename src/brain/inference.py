"""Main brain inference orchestrator.

Pipeline: mode routing → retrieval → prompt building → inference → FactGuard
verification → response formatting.
"""
from __future__ import annotations

import hashlib
import importlib
import logging
import time
import time as _time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from src.brain.config import get_brain_settings
from src.brain.mode_router import BrainMode, route_mode
from src.brain.ollama_client import MODE_PROFILES, OllamaClient
from src.brain.prompt_builder import build_prompt
from src.brain.response_formatter import BrainResponse, Citation, strip_think_tags
from src.brain.retriever import BrainRetriever, RetrievedChunk
from src.brain.tailor_schema import TailorPlan, parse_tailor_plan, tailor_json_schema
from src.brain.telemetry import append_telemetry
from src.brain.validator import (
    corpus_entity_set, employer_of, extract_entities, slug_employer,
    validate_tailor_output,
)

logger = logging.getLogger(__name__)


def make_cache_key(mode: str, job_desc: str, section_tag: str, query: str) -> str:
    jd = hashlib.sha256((job_desc or "").encode("utf-8")).hexdigest()
    q = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()
    return f"{mode}::{jd}::{section_tag or '-'}::{q}"


_PSEUDO_COMPANY_MARKERS = ("master resume",)  # doc-title node typed Company (data hygiene)


def enumerate_sections(chunks=None) -> List[str]:
    """['skills'] + experience@<employer> per real employer (spec §5.9 step 1).

    B1: employers = (sources of LED_STORY edges ∩ Company-node names) ∪
    story-chunk ``metadata.company`` (∩ Company-node names), minus
    pseudo-companies. Other ownership relations are excluded because real
    data (profiled 2026-08-27) carries story titles ('Story 7 - ...'), role
    names ('Software Engineer') and the doc-title itself as edge sources —
    enumerating them would spawn ~30 fake sections, each a ~30 s brain call.
    Deviation from plan Rev 1.1: on today's MASTER_RESUME.jsonl the LED_STORY
    edge sources are role titles, not companies, so the edge-intersection
    alone yields zero sections; the story chunks' direct ``metadata.company``
    (all 18 stories, verified 2026-08-27) is the second employer source. The
    Company-node-name intersection keeps unverified names out either way."""
    from src.brain.validator import _load_chunks, slug_employer, master_resume_jsonl_path
    cs = chunks if chunks is not None else _load_chunks(master_resume_jsonl_path())
    company_names = {str((c.get("metadata") or {}).get("name")).strip()
                     for c in cs
                     if c.get("type") == "graph_node"
                     and (c.get("metadata") or {}).get("node_type") == "Company"}
    employers = []
    for c in cs:
        if c.get("type") != "story":
            continue
        comp = str((c.get("metadata") or {}).get("company", "")).strip()
        if (comp in company_names
                and not any(mk in comp.lower() for mk in _PSEUDO_COMPANY_MARKERS)
                and comp not in employers):
            employers.append(comp)
    for c in cs:
        meta = c.get("metadata") or {}
        if c.get("type") != "graph_edge" or meta.get("relation") != "LED_STORY":
            continue
        src = str(meta.get("source", "")).strip()
        if (src in company_names
                and not any(mk in src.lower() for mk in _PSEUDO_COMPANY_MARKERS)
                and src not in employers):
            employers.append(src)
    return ["skills"] + [f"experience@{slug_employer(e)}" for e in employers]


def reduce_section_plans(ordered: List[Tuple[str, TailorPlan]]) -> Dict[str, Any]:
    """Deterministic reduce (spec §5.9 step 3): cross-section source uniqueness,
    skills union by first emergence, warnings on collisions.

    B2: claims are keyed by owning section — a bullet citing its own section's
    listed story is one claim, not a collision (canonical §3.3 shape). Rank on
    cross-section collision = enumeration order; earlier section wins
    (spec §5.9 Rev 4.1)."""
    claimed_by: Dict[str, str] = {}
    plans: Dict[str, TailorPlan] = {}
    merged_skills: List[str] = []
    gaps: List[str] = []
    warnings: List[str] = []

    def claim(item_id: str, section: str, kind: str) -> bool:
        owner = claimed_by.get(item_id)
        if owner is None:
            claimed_by[item_id] = section
            return True
        if owner == section:
            return True
        warnings.append(f"reduce collision: {section} {kind} {item_id} already claimed by {owner}")
        return False

    for section, plan in ordered:
        p = plan.model_copy(deep=True)
        kept_bullets = [b for b in p.bullets if claim(b.source, section, "bullet source")]
        kept_stories = [s for s in p.stories if claim(s.id, section, "story")]
        p.bullets, p.stories = kept_bullets, kept_stories
        for skill in p.skills_to_emphasize:
            if skill not in merged_skills:
                merged_skills.append(skill)
        for g in p.gaps:
            if g not in gaps:
                gaps.append(g)
        plans[section] = p
    return {"plans": plans, "merged_skills": merged_skills,
            "global_gaps": gaps, "warnings": warnings}


class BrainInference:
    """Orchestrate brain queries: mode routing → retrieval → inference → verification."""

    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        retriever: Optional[BrainRetriever] = None,
        enable_cache: bool = True,
    ) -> None:
        self.settings = get_brain_settings()
        self.ollama = ollama_client or OllamaClient()
        self.retriever = retriever or BrainRetriever()
        self.enable_cache = enable_cache
        self._cache: "OrderedDict[str, BrainResponse]" = OrderedDict()

    def _cache_put(self, key: str, response: "BrainResponse") -> None:
        self._cache[key] = response
        self._cache.move_to_end(key)
        while len(self._cache) > self.settings.BRAIN_CACHE_MAX_SIZE:
            self._cache.popitem(last=False)

    def clear_cache(self) -> None:
        """Clear all cached responses."""
        self._cache.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(
        self,
        query: str,
        mode: str = "auto",
        job_desc: Optional[str] = None,
        top_k: Optional[int] = None,
        use_cache: bool = True,
    ) -> BrainResponse:
        """Execute a brain query end-to-end with optional LRU exact-match caching.

        Args:
            query: User's natural-language question or request.
            mode: Override mode (``auto`` lets the router decide).
            job_desc: Optional job description for tailoring mode.
            top_k: Retrieval depth override.
            use_cache: Whether to check and populate in-memory response cache.

        Returns:
            :class:`BrainResponse` with answer, citations, confidence, etc.
        """
        start_time = time.time()
        top_k = top_k or self.settings.BRAIN_RETRIEVAL_TOP_K

        # 1. Route mode
        brain_mode = route_mode(query, mode=mode, job_desc=job_desc)

        # Cache check for deterministic identical requests
        cache_key = make_cache_key(brain_mode.value, job_desc or "", "", query)
        cached = self._cache.get(cache_key) if self.enable_cache and use_cache else None
        if cached is not None:
            self._cache.move_to_end(cache_key)
            return BrainResponse(
                answer=cached.answer,
                mode=cached.mode,
                citations=cached.citations,
                confidence=cached.confidence,
                warnings=cached.warnings,
                retrieved_chunks=cached.retrieved_chunks,
                latency_ms=(time.time() - start_time) * 1000,
            )

        # 2. Retrieve relevant chunks
        chunks = self.retriever.retrieve(
            query, brain_mode, top_k=top_k, job_desc=job_desc
        )

        # 3. Build prompt
        prompt = build_prompt(query, brain_mode, chunks, job_desc=job_desc)

        # 4. Generate response (local Ollama → cloud fallback)
        if self.ollama.is_available():
            answer = self.ollama.generate(prompt, mode=brain_mode.value)
        elif self.settings.BRAIN_FALLBACK_TO_CLOUD:
            logger.warning("Ollama unavailable, falling back to cloud LLM gateway")
            answer = self._cloud_fallback(prompt)
        else:
            return BrainResponse(
                answer="Brain service unavailable. Ollama is not running.",
                mode=brain_mode.value,
                warnings=["Ollama unavailable and cloud fallback disabled"],
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Strip reasoning tags emitted by thinking models (e.g. Qwen3 / DeepSeek)
        answer = strip_think_tags(answer)

        # 5. Verify with FactGuard
        warnings: List[str] = []
        confidence: float = 1.0
        if self.settings.BRAIN_FACTGUARD_ENABLED:
            warnings, confidence = self._verify_with_factguard(answer, chunks)

        # 6. Build citations from retrieved chunks
        citations = [
            Citation(chunk_id=c.id, relevance=c.score, chunk_type=c.chunk_type)
            for c in chunks
        ]

        latency_ms = (time.time() - start_time) * 1000

        result = BrainResponse(
            answer=answer,
            mode=brain_mode.value,
            citations=citations,
            confidence=confidence,
            warnings=warnings,
            retrieved_chunks=len(chunks),
            latency_ms=latency_ms,
        )

        if self.enable_cache and use_cache:
            self._cache_put(cache_key, result)

        return result

    def batch_query(
        self,
        queries: List[str],
        mode: str = "qa",
        job_desc: Optional[str] = None,
        top_k: Optional[int] = None,
        use_cache: bool = True,
    ) -> List[BrainResponse]:
        """Execute a batch of related queries sharing retrieved context chunks and session state.

        Saves ~50% retrieval and initialization latency on multi-question application forms.
        """
        if not queries:
            return []

        top_k = top_k or self.settings.BRAIN_RETRIEVAL_TOP_K
        brain_mode = route_mode(queries[0], mode=mode, job_desc=job_desc)

        # Retrieve shared context chunks once using combined query or job_desc
        combined_query = " ".join(queries)
        shared_chunks = self.retriever.retrieve(
            combined_query, brain_mode, top_k=top_k, job_desc=job_desc
        )

        results: List[BrainResponse] = []
        for q in queries:
            start_q = time.time()
            cache_key = f"{brain_mode.value}::{q.strip().lower()}::{job_desc or ''}"
            cached = self._cache.get(cache_key) if self.enable_cache and use_cache else None
            if cached is not None:
                self._cache.move_to_end(cache_key)
                results.append(cached)
                continue

            prompt = build_prompt(q, brain_mode, shared_chunks, job_desc=job_desc)

            if self.ollama.is_available():
                answer = self.ollama.generate(prompt, mode=brain_mode.value)
            elif self.settings.BRAIN_FALLBACK_TO_CLOUD:
                answer = self._cloud_fallback(prompt)
            else:
                answer = "Brain service unavailable. Ollama is not running."

            answer = strip_think_tags(answer)

            warnings: List[str] = []
            confidence: float = 1.0
            if self.settings.BRAIN_FACTGUARD_ENABLED:
                warnings, confidence = self._verify_with_factguard(answer, shared_chunks)

            citations = [c.id for c in shared_chunks if c.id]
            res = BrainResponse(
                answer=answer,
                mode=brain_mode.value,
                citations=citations,
                confidence=confidence,
                warnings=warnings,
                retrieved_chunks=len(shared_chunks),
                latency_ms=(time.time() - start_q) * 1000,
            )
            if self.enable_cache and use_cache:
                self._cache_put(cache_key, res)
            results.append(res)

        return results

    def query_stream(self, query: str, mode: str = "auto", job_desc=None, top_k=None):
        """Streaming query: yields {'token': str}... then {'response': dict} (spec §5.8)."""
        top_k = top_k or self.settings.BRAIN_RETRIEVAL_TOP_K
        brain_mode = route_mode(query, mode=mode, job_desc=job_desc)
        chunks = self.retriever.retrieve(query, brain_mode, top_k=top_k, job_desc=job_desc)
        prompt = build_prompt(query, brain_mode, chunks, job_desc=job_desc)
        parts: List[str] = []
        if self.ollama.is_available():
            for tok in self.ollama.generate_stream(prompt, mode=brain_mode.value):
                parts.append(tok)
                yield {"token": tok}
            answer = strip_think_tags("".join(parts))
        elif self.settings.BRAIN_FALLBACK_TO_CLOUD:
            answer = self._cloud_fallback(prompt)
        else:
            answer = "Brain service unavailable. Ollama is not running."
        warnings: List[str] = []
        confidence = 1.0
        if self.settings.BRAIN_FACTGUARD_ENABLED:
            warnings, confidence = self._verify_with_factguard(answer, chunks)
        res = BrainResponse(answer=answer, mode=brain_mode.value, confidence=confidence,
                            warnings=warnings, retrieved_chunks=len(chunks))
        yield {"response": res.to_dict()}

    def tailor_resume_sections(self, job_desc: str, top_k: Optional[int] = None) -> Dict[str, Any]:
        """Sectioned map-reduce full-resume tailoring (spec §5.9)."""
        top_k = top_k or self.settings.BRAIN_RETRIEVAL_TOP_K
        schema = tailor_json_schema()
        jd_entities = extract_entities(job_desc)
        sections = enumerate_sections()  # read MASTER_RESUME.jsonl once
        ordered: List[Tuple[str, TailorPlan]] = []
        warnings: List[str] = []
        # Truncation-watchdog denominator for telemetry (spec §5.8): the
        # context window the tailoring profile actually requests.
        num_ctx = MODE_PROFILES[OllamaClient.resolve_profile("tailoring")]["num_ctx"]
        for section in sections:
            scope_employer = section.split("@", 1)[1] if "@" in section else None
            chunks = self.retriever.retrieve(
                f"{section} {job_desc[:200]}", BrainMode.TAILORING,
                top_k=top_k * 2, job_desc=job_desc)
            if scope_employer:
                owned = [c for c in chunks if employer_of(c.id) is not None]
                if len(owned) < len(chunks):
                    warnings.append(f"section {section}: {len(chunks) - len(owned)} unowned chunks excluded (hard filter, M5)")
                chunks = [c for c in owned
                          if slug_employer(employer_of(c.id) or "") == scope_employer]
            prompt = build_prompt("Tailor this resume section for the job description.",
                                  BrainMode.TAILORING, chunks, job_desc=job_desc, section=section)
            cache_key = make_cache_key("tailoring", job_desc, section, "section-plan")
            plan = self._cache.get(cache_key)
            cache_hit = plan is not None  # M2: record the hit BEFORE any generation
            started = _time.time()
            integrity_violations = 0
            if plan is None:
                raw = self.ollama.generate(prompt, mode="tailoring", format=schema)
                plan = parse_tailor_plan(raw, repair=lambda r: self.ollama.generate(
                    prompt + "\n\nPrevious output was invalid JSON. Respond with valid JSON only.",
                    mode="tailoring", format=schema))
                if plan is not None:
                    chunk_ids = {c.id for c in chunks}
                    chunk_entities = {c.id: extract_entities(c.content) for c in chunks}
                    gate = validate_tailor_output(plan, chunk_ids, chunk_entities,
                                                  section, jd_entities=jd_entities,
                                                  corpus_entities=corpus_entity_set())
                    plan = gate.plan
                    integrity_violations = len(gate.drops)  # canary plan_integrity signal
                    warnings.extend(gate.drops + gate.warnings)
                    self._cache_put(cache_key, plan)
            record: Dict[str, Any] = {
                # M2: resolved, not constructor default; str() keeps the
                # record JSON-serializable for stub clients in tests.
                "model": str(self.ollama.resolve_model("tailoring", None)),
                "mode": "tailoring", "section": section, "cache_hit": cache_hit,
                "wall_sec": round(_time.time() - started, 2),
                "factguard_verdict": "pass" if plan is not None else "invalid",
                "num_ctx": num_ctx,
                "format_fail": plan is None,
                "plan_integrity_violations": integrity_violations,
            }
            meta = getattr(self.ollama, "last_meta", None)  # truncation watchdog (spec §5.8)
            if isinstance(meta, dict) and isinstance(meta.get("prompt_eval_count"), int):
                record["prompt_eval_count"] = meta["prompt_eval_count"]
            append_telemetry(record)
            if plan is None:
                warnings.append(f"section {section}: no valid plan (degraded to no-changes)")
                continue
            ordered.append((section, plan))
        reduced = reduce_section_plans(ordered)
        append_telemetry({
            "model": str(self.ollama.resolve_model("tailoring", None)),
            "mode": "tailoring", "section": "__reduce__",
            "reduce_collisions": sum(1 for w in reduced["warnings"]
                                     if w.startswith("reduce collision")),
        })
        sectioned: Dict[str, Optional[TailorPlan]] = {s: None for s in sections}
        sectioned.update(reduced["plans"])
        reduced["plans"] = sectioned
        reduced["warnings"] = warnings + reduced["warnings"]
        reduced["confidence"] = max(0.0, 1.0 - 0.1 * len(reduced["warnings"]))
        return reduced

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _cloud_fallback(self, prompt: str) -> str:
        """Fall back to cloud LLM gateway when Ollama is unavailable."""
        import asyncio

        from src.core.gateway import get_gateway

        gateway = get_gateway()
        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(
                gateway.chat(messages=[{"role": "user", "content": prompt}])
            )
            return response
        finally:
            loop.close()

    def _verify_with_factguard(
        self, answer: str, chunks: List[RetrievedChunk]
    ) -> Tuple[List[str], float]:
        """Verify *answer* against source *chunks* using the existing FactGuard.

        Returns:
            ``(warnings, confidence)`` where confidence ∈ [0, 1].
        """
        try:
            # The directory name starts with a digit → use importlib.
            fact_guard_mod = importlib.import_module(
                "src.pipeline.3_tailoring.fact_guard"
            )
            FactGuard = fact_guard_mod.FactGuard

            guard = FactGuard()
            is_valid, reason = guard.validate_bullet(answer)

            if is_valid:
                return [], 1.0

            # Violation detected — emit warning and reduce confidence.
            warnings = [reason]
            confidence = max(0.0, min(1.0, 0.5 if not is_valid else 0.8))
            return warnings, confidence
        except Exception as exc:
            logger.warning("FactGuard verification failed: %s", exc)
            return [], 0.8  # Default confidence when FactGuard is unavailable
