"""Synthesize training pairs from MASTER_RESUME.jsonl using LLM teacher."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

from src.brain.config import get_brain_settings

PROMPTS_DIR = Path(__file__).parent / "prompts"

import logging
import re

logger = logging.getLogger(__name__)

# Chunk types that generate training pairs
SYNTHESIZABLE_TYPES = {
    "story": 4,           # 4 Q&A variants per story
    "skill_category": 4,  # 4 per skill category
    "summary": 3,         # 3 per summary
    "summary_variant": 3, # 3 per variant
    "graph_node": 2,      # 2 per graph node (only Technology/ImpactMetric types)
    "project": 3,         # 3 per project
    "education": 1,       # 1 per education entry
    "certification": 1,   # 1 per cert
    "contact": 1,         # 1 for contact
}

# Graph node types worth synthesizing (legacy synthesize_all path; do NOT widen —
# controller ruling 2026-08-27. Factual facet volume comes from FACT_QUESTIONS
# breadth in the driver, not from this set.)
SYNTHESIZABLE_NODE_TYPES = {"Technology", "ImpactMetric", "STAR_Story", "Project"}

# Factual facet question banks (spec §3.4, plan Rev 1.3): "{name}" formatted with
# the node's metadata name. Every node_type present in MASTER_RESUME.jsonl gets a
# bank — the driver's factual enumeration covers node types listed here (plus
# SYNTHESIZABLE_NODE_TYPES). DEFAULT_FACT_QUESTIONS is NOT a data-drift
# backstop: the driver skips node types absent from both, so a new type trains
# nothing silently. test_fact_banks_cover_corpus_node_types is the real alarm.
FACT_QUESTIONS = {
    "Technology": [
        "What is your hands-on experience with {name}?",
        "Why did {name} matter in your work?",
        "Compare {name} to alternatives you have used.",
    ],
    "ImpactMetric": [
        "Which metric are you most proud of and how was it measured — {name}?",
        "Walk me through how {name} was calculated and what drove it.",
    ],
    "STAR_Story": [
        "Why did {name} matter in your career?",
        "What would you do differently after {name}?",
    ],
    "Project": [
        "Why did you take on {name}, and what was your role?",
        "What outcome from {name} would you highlight?",
    ],
    "TechCategory": [
        "What is your experience across the {name} side of your stack?",
        "How has {name} shaped the way you design systems?",
        "Which tools do you reach for under {name}, and why?",
    ],
    "Action": [
        "What does your day-to-day work under {name} actually look like?",
        "How deep is your ownership of {name}?",
        "What is the hardest problem you handled within {name}?",
    ],
    "Result": [
        "What results did {name} produce, and how were they measured?",
        "Why does {name} stand out in your track record?",
        "What would you repeat from {name}, and what would you change?",
    ],
    "CompetencyDimension": [
        "Where have you demonstrated {name} in production?",
        "What is your strongest example of {name}, and what was the outcome?",
    ],
    "Role": [
        "What did {name} involve for you, day to day?",
        "How did working in {name} shape your engineering approach?",
    ],
    "Company": [
        "What did you work on at {name}, and what was your impact?",
        "Why does your time at {name} matter to your career story?",
    ],
    "PatternCategory": [
        "How have you applied {name} in your systems?",
        "What problem does {name} solve in your work?",
    ],
    "ArchitecturalPattern": [
        "Where have you used {name}, and what did it buy you?",
        "When is {name} the wrong choice, based on your experience?",
    ],
    "MacroDomain": [
        "How deep is your experience in {name}?",
        "What work best demonstrates your grounding in {name}?",
    ],
    "Reflection": [
        "What is the lesson behind {name}?",
        "How did {name} change the way you work?",
    ],
    "Situation": [
        "What made {name} hard, and what did you do first?",
        "How did you resolve {name}?",
    ],
}
DEFAULT_FACT_QUESTIONS = [
    "What is {name} and why is it in your background?",
    "How has {name} shown up in your work?",
    "Where do you stand with {name} today?",
]

# Avatar facet: persona questions served over summary/summary_variant/role chunks.
AVATAR_QUESTIONS = [
    "Introduce yourself and your career arc.",
    "What kind of engineer are you, in your own words?",
    "Which teams or companies shaped how you work, and how?",
    "What is the most meaningful problem you have solved so far?",
    "How do you decide what to learn next?",
    "What do you want your next role to look like, and why?",
    "How would you describe your leadership style?",
    "What mistake changed the way you work?",
    "What do colleagues consistently rely on you for?",
    "Where are you heading over the next five years?",
]


def _to_chunk(c):
    """Normalize a raw JSONL chunk dict to RetrievedChunk; pass objects through."""
    if isinstance(c, dict):
        from src.brain.retriever import RetrievedChunk
        return RetrievedChunk(id=c.get("id", ""), content=c.get("content", ""),
                              score=1.0, chunk_type=c.get("type", "unknown"),
                              metadata=c.get("metadata") or {})
    return c



def _extract_and_parse_json(raw: str) -> Any:
    """Robustly extract and parse JSON from LLM response."""
    if not raw:
        return {}
    cleaned = raw.strip()
    # Strip markdown code blocks if present
    if "```" in cleaned:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback: try finding outermost JSON object or array
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(cleaned[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass
        first_bracket = cleaned.find("[")
        last_bracket = cleaned.rfind("]")
        if first_bracket != -1 and last_bracket > first_bracket:
            try:
                return json.loads(cleaned[first_bracket:last_bracket + 1])
            except json.JSONDecodeError:
                pass
        raise


@dataclass
class SynthesisReport:
    total_chunks: int = 0
    total_pairs: int = 0
    pairs_by_type: Dict[str, int] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class Synthesizer:
    """Generate training pairs from JSONL chunks using LLM teacher model."""

    def __init__(self, teacher_model: str = None, retriever=None):
        if teacher_model is None:
            from src.brain.config import get_brain_settings as _gs
            teacher_model = _gs().BRAIN_TEACHER_MODEL  # spec §3.2: explicit teacher
        self.teacher_model = teacher_model
        self.retriever = retriever  # None -> lazy BrainRetriever in facet methods
        self.jinja_env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
        self.settings = get_brain_settings()
        # (fix wave F2: reject reasons are returned per call — never instance state)

    def load_chunks(self, jsonl_path: Path) -> List[Dict[str, Any]]:
        """Load all chunks from JSONL file."""
        chunks = []
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    chunks.append(json.loads(line))
        return chunks

    def is_synthesizable(self, chunk: Dict[str, Any]) -> bool:
        """Check if a chunk type should generate training pairs."""
        chunk_type = chunk.get("type", "")
        if chunk_type in SYNTHESIZABLE_TYPES:
            return True
        if chunk_type == "graph_node":
            node_type = (chunk.get("metadata") or {}).get("node_type", "")
            return node_type in SYNTHESIZABLE_NODE_TYPES
        return False

    def _get_template_name(self, chunk: Dict[str, Any]) -> str:
        """Map chunk type to Jinja2 template."""
        chunk_type = chunk.get("type", "")
        if chunk_type == "story":
            return "synthesize_story.j2"
        elif chunk_type == "skill_category":
            return "synthesize_skill.j2"
        elif chunk_type in ("summary", "summary_variant"):
            return "synthesize_summary.j2"
        elif chunk_type == "graph_node":
            return "synthesize_graph_node.j2"
        else:
            return "synthesize_story.j2"  # fallback

    async def _call_teacher(
        self, prompt: str, json_mode: bool = True, max_retries: int = 3, backoff_base: float = 2.0
    ) -> str:
        """Call teacher model via Alibaba provider directly (no fallback chain).
        json_mode=True sets response_format=json_object, which the Alibaba
        endpoint rejects (HTTP 400) unless the prompt itself contains the word
        "json" — true for tailor/legacy JSON-schema templates, FALSE for the
        serving-path prose templates (qa/avatar/letter). Live-verified
        2026-08-27: every prose teacher call 400s with json_mode=True, so
        _qa_pair and synthesize_letter pass json_mode=False.

        Includes retry-with-backoff for network read timeouts / connection drops.
        """
        import asyncio
        from src.core.gateway import get_gateway
        gateway = get_gateway()
        # Use Alibaba provider directly to avoid fallback to Gemini/OpenRouter
        loop = asyncio.get_event_loop()

        for attempt in range(1, max_retries + 1):
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: gateway.alibaba_provider.generate(
                        prompt=prompt,
                        json_mode=json_mode,
                        temperature=0.7,
                        model=self.teacher_model,
                        timeout=120,
                    )
                )
                return response
            except Exception as e:
                if attempt == max_retries:
                    logger.error(
                        "Teacher call failed after %d attempts: %s", max_retries, e
                    )
                    raise
                delay = backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    "Teacher call attempt %d/%d failed: %s; retrying in %.1fs...",
                    attempt, max_retries, e, delay
                )
                await asyncio.sleep(delay)
        raise RuntimeError("Teacher call retries exhausted")

    async def synthesize_chunk(self, chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate training pairs for a single chunk."""
        chunk_type = chunk.get("type", "")
        num_variants = SYNTHESIZABLE_TYPES.get(chunk_type, 2)

        template_name = self._get_template_name(chunk)
        template = self.jinja_env.get_template(template_name)
        # Ensure metadata is always a dict for Jinja2 template access
        chunk_for_template = dict(chunk)
        chunk_for_template["metadata"] = chunk.get("metadata") or {}
        prompt = template.render(chunk=chunk_for_template, num_variants=num_variants)

        try:
            raw_response = await self._call_teacher(prompt)
            parsed = _extract_and_parse_json(raw_response)
            if isinstance(parsed, list):
                pairs = parsed
            elif isinstance(parsed, dict):
                pairs = parsed.get("pairs", [])
                if not pairs and "question" in parsed and "answer" in parsed:
                    pairs = [{"question": parsed["question"], "answer": parsed["answer"]}]
            else:
                pairs = []
        except Exception as e:
            logger.warning("Failed to synthesize chunk %s: %s", chunk.get("id"), e)
            return []

        # Convert to training pair format
        training_pairs = []
        system_prompt = self._get_system_prompt(chunk_type)
        for pair in pairs:
            if not isinstance(pair, dict) or not pair.get("question") or not pair.get("answer"):
                continue
            training_pairs.append({
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": pair["question"]},
                    {"role": "assistant", "content": pair["answer"]},
                ],
                "metadata": {
                    "source_chunk_id": chunk.get("id", ""),
                    "source_chunk_type": chunk_type,
                    "mode": self._infer_mode(chunk_type),
                    "synthesis_model": self.teacher_model,
                },
            })
        return training_pairs

    def _get_system_prompt(self, chunk_type: str) -> str:
        """Get system prompt based on chunk type."""
        if chunk_type in ("story", "project"):
            return "You are Alex Rivera, a software engineer. Answer in first person."
        elif chunk_type == "skill_category":
            return "You are Alex Rivera. Describe your technical experience."
        else:
            return "You are Alex Rivera, a software engineer with 10+ years of experience."

    def _infer_mode(self, chunk_type: str) -> str:
        """Infer the brain mode for this chunk type."""
        if chunk_type in ("story", "project", "summary", "summary_variant"):
            return "avatar"
        elif chunk_type == "skill_category":
            return "qa"
        else:
            return "qa"

    async def synthesize_all(
        self, jsonl_path: Path, output_path: Optional[Path] = None, dry_run: bool = False
    ) -> SynthesisReport:
        """Synthesize training pairs from all chunks."""
        start_time = time.time()
        chunks = self.load_chunks(jsonl_path)
        synthesizable = [c for c in chunks if self.is_synthesizable(c)]

        report = SynthesisReport(total_chunks=len(chunks))
        all_pairs = []

        for chunk in synthesizable:
            try:
                pairs = await self.synthesize_chunk(chunk)
                all_pairs.extend(pairs)
                chunk_type = chunk.get("type", "unknown")
                report.pairs_by_type[chunk_type] = report.pairs_by_type.get(chunk_type, 0) + len(pairs)
                report.total_pairs += len(pairs)
            except Exception as e:
                report.failures.append(f"{chunk.get('id', 'unknown')}: {str(e)}")

        report.duration_seconds = time.time() - start_time

        if not dry_run and output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                for pair in all_pairs:
                    f.write(json.dumps(pair, ensure_ascii=False) + "\n")

        return report

    async def synthesize_tailor_sections(self, job: Dict[str, Any], top_k: int = 6):
        """G1 tailor corpus: one gate-passed section plan per enumerated section.
        User message = exact serving prompt (P8); assistant = validated plan JSON.
        Returns ``(pairs, reject_details)`` — reject_details is a list of
        ``{"job_id", "section", "reason"}`` rows (reason in no_chunks |
        teacher_fail | parse_fail | gate_drop; spec §3.2 flywheel mining)."""
        from src.brain.inference import enumerate_sections
        from src.brain.mode_router import BrainMode
        from src.brain.prompt_builder import build_prompt
        from src.brain.retriever import BrainRetriever
        from src.brain.tailor_schema import parse_tailor_plan
        from src.brain.validator import (corpus_entity_set, employer_of,
                                         extract_entities, slug_employer,
                                         validate_tailor_output)
        retriever = self.retriever or BrainRetriever()
        jd = job["jd"]
        jd_entities = extract_entities(jd)
        pairs, rejects = [], []

        def _reject(section, reason, detail=None):
            row = {"job_id": job.get("job_id"), "section": section,
                   "reason": reason}
            if detail:  # 2026-08-28 smoke diagnosis: which validator check fired
                row["detail"] = list(detail)[:5]
            rejects.append(row)

        for section in enumerate_sections():
            scope_employer = section.split("@", 1)[1] if "@" in section else None
            # v2.5 (2026-08-28): the section SLUG ("experience@london_
            # computer_systems", underscores) polluted the RRF query ->
            # employer sections retrieved nothing (no_chunks = 53% of rejects
            # in the killed full run). Offline A/B/C over the 470-JD pool
            # (coverage_check.py, zero calls): jd-only 52% < jd-only k16 66%
            # < HUMANIZED employer name + JD 97.7%. Query = employer name
            # (or 'skills') + jd; ownership still enforced by the
            # slug_employer hard filter below.
            human = scope_employer.replace("_", " ") if scope_employer else "skills"
            chunks = retriever.retrieve(f"{human} {jd[:250]}", BrainMode.TAILORING,
                                        top_k=10, job_desc=jd)
            if scope_employer:
                chunks = [c for c in chunks
                          if slug_employer(employer_of(c.id) or "") == scope_employer]
            if not chunks:
                _reject(section, "no_chunks")
                continue
            prompt = build_prompt("Tailor this resume section for the job description.",
                                  BrainMode.TAILORING, chunks, job_desc=jd, section=section)
            try:
                raw = await self._call_teacher(prompt)
            except Exception as e:
                logger.warning("Teacher call failed for section %s: %s", section, e)
                _reject(section, "teacher_fail", detail=[str(e)[:160]])
                continue
            plan = parse_tailor_plan(raw)
            if plan is None:
                _reject(section, "parse_fail")
                continue
            chunk_ids = {c.id for c in chunks}
            chunk_entities = {c.id: extract_entities(c.content) for c in chunks}
            # chunks=None: scope re-check resolves against the REAL
            # MASTER_RESUME index (doubles enforcement with the pre-filter);
            # corpus_entities feeds the gaps reverse-verification gate.
            gate = validate_tailor_output(plan, chunk_ids, chunk_entities, section,
                                          jd_entities=jd_entities,
                                          chunks=None,
                                          corpus_entities=corpus_entity_set())
            if gate.drops or not gate.plan.bullets and not gate.plan.stories:
                _reject(section, "gate_drop", detail=gate.drops or ["empty_plan"])
                continue
            pairs.append({
                "messages": [
                    {"role": "system", "content": _SYSTEM_TAILOR},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": gate.plan.model_dump_json()},
                ],
                "metadata": {"mode": "tailoring", "facet": "tailor_resume",
                             "section": section, "job_id": job.get("job_id"),
                             "chunk_ids": sorted(chunk_ids),
                             "synthesis_model": self.teacher_model},
            })
        return pairs, rejects

    # Canned teacher-template refusals + meta narration (fix wave F4,
    # 2026-08-28): pilot-contamination showed "I don't have that information."
    # passes the entity gate vacuously (0 entities). These must be rejected
    # with an explicit reason so they never enter the corpus.
    _REFUSAL_RE = re.compile(
        r"i don'?t have that information|i don'?t have direct experience|"
        r"the (provided )?context (does not|doesn'?t)|not explicitly stated|"
        r"not in the (provided )?context|there is no information|"
        r"i (cannot|can'?t) (find|answer|say|help)\b", re.IGNORECASE)

    async def _qa_pair(self, question: str, chunks, *, mode: str, facet: str,
                       tol_floor: int = 1, brain_mode=None, min_words: int = 0):
        """Shared qa-facet engine (serving-prompt parity, P8; grounding check).
        Returns ``(pair, reason)`` with reason None on success or one of
        no_chunks | teacher_fail | parse_fail | refusal | third_person |
        too_short | ungrounded. Reasons are returned, never stashed on
        instance state (fix wave F2: 4 concurrent driver tasks shared
        ``last_reject_reason`` and masked each other's reasons).
        ``brain_mode``: explicit template override (avatar facet). When None
        the template is resolved with the SERVE router itself,
        ``route_mode(question)`` — behavioral "tell me about a time" and
        "your experience" questions serve avatar.j2 (first person), factual
        what/how questions serve qa.j2; training a question on the wrong
        template breaks P8 (fix wave F3, same class as T13-I1).
        First-person contract (spec §3.4 "answers = first-person STAR prose")
        applies to AVATAR-routed questions: name mentions ("Alex") and
        template-echoing meta prose are rejected as third_person.
        ``tol_floor`` widens the ungrounded budget for persona prose (spec §3.4
        avatar answers name employers/services spread across the whole summary
        set, not just the anchor chunks). ``min_words`` is a per-facet floor —
        canned one-liners must not pass as STAR prose."""
        from src.brain.mode_router import BrainMode, route_mode
        from src.brain.prompt_builder import build_prompt
        from src.brain.validator import extract_entities
        if not chunks:
            return None, "no_chunks"
        resolved = brain_mode or route_mode(question)
        first_person = resolved is BrainMode.AVATAR
        prompt = build_prompt(question, resolved, chunks)
        try:
            answer = await self._call_teacher(prompt, json_mode=False)
        except Exception as e:
            logger.warning("Teacher call failed for %s query: %s", facet, e)
            return None, "teacher_fail"
        if not (answer or "").strip():
            return None, "parse_fail"
        if self._REFUSAL_RE.search(answer):
            return None, "refusal"
        if first_person and re.search(r"\balex\b", answer, re.IGNORECASE) \
                and not re.search(r"\b(i|me|my|we|our)\b", answer, re.IGNORECASE):
            # Name SELF-disclosure ("I'm Alex Rivera, …") is legal first
            # person; third-person NARRATION ("Alex led …") is not.
            return None, "third_person"
        if min_words and len(answer.split()) < min_words:
            return None, "too_short"
        from src.brain.validator import grounding_token_pool
        pool = set()
        for c in chunks:
            # F1b: chunk text is evidence at ANY position (leading tokens of
            # short anchor chunks would otherwise be invisible to the pool).
            pool |= extract_entities(getattr(c, "content", "") or "")
            pool |= grounding_token_pool(getattr(c, "content", "") or "")
        # F6: the candidate's own name is persona (system prompt), not a
        # fabricated entity — third-person qa-voice answers say "Alex Rivera".
        pool |= {"alex", "rivera"}
        answer_ents = extract_entities(answer)
        ungrounded = answer_ents - pool
        budget = max(tol_floor if not first_person else 2, len(answer_ents) // 5)
        if len(ungrounded) > budget:
            return None, "ungrounded"
        pair = {
            "messages": [
                {"role": "system", "content": "You are Alex Rivera, a software engineer. Answer in first person."},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer},
            ],
            "metadata": {"mode": mode, "facet": facet,
                         "chunk_ids": [getattr(c, "id", None) for c in chunks],
                         "synthesis_model": self.teacher_model},
        }
        return pair, None

    async def synthesize_behavioral(self, question: str, chunks):
        """QA corpus: grounded first-person STAR prose for one behavioral
        question (spec §3.4). Returns ``(pair, reason)``. Template resolved by
        route_mode in _qa_pair — behavioral archetypes ("tell me about a
        time…") serve avatar.j2 first-person, so synth must train on it too
        (fix wave F3)."""
        return await self._qa_pair(question, chunks, mode="qa",
                                   facet="behavioral", min_words=25)

    async def synthesize_fact_node(self, node_chunk, extra_chunks,
                                   question: Optional[str] = None):
        """QA corpus: grounded factual pair anchored on one graph_node chunk.
        The node is always inside the grounding chunk list; with no extras the
        retriever grounds the node against its own neighbourhood (Task 13)."""
        from src.brain.mode_router import BrainMode
        node = _to_chunk(node_chunk)
        extras = [_to_chunk(c) for c in (extra_chunks or [])]
        if not extras:
            try:
                retriever = self.retriever
                if retriever is None:
                    from src.brain.retriever import BrainRetriever
                    retriever = self.retriever = BrainRetriever()
                extras = [_to_chunk(c) for c in
                          retriever.retrieve(node.content or node.id, BrainMode.QA, top_k=2)]
            except Exception as e:
                logger.warning("Fact-node grounding retrieval failed for %s: %s", node.id, e)
                extras = []
        if question is None:
            md = ((node_chunk.get("metadata") or {}) if isinstance(node_chunk, dict)
                  else (getattr(node, "metadata", {}) or {}))
            name = str(md.get("name") or node.content)
            bank = FACT_QUESTIONS.get(md.get("node_type", "")) or DEFAULT_FACT_QUESTIONS
            question = bank[0].format(name=name)
        return await self._qa_pair(question, [node] + extras,
                                   mode="qa", facet="factual", min_words=10)

    async def synthesize_legacy(self, question: str, chunks):
        """Spec §3.4 remainder: re-synthesize the legacy v1 qa corpus (the 386
        `training_pairs.jsonl` questions) into the grounded format — chunks
        come from the SERVE retrieval path, template from route_mode (fix
        wave F5). Returns ``(pair, reason)`` like the other qa facets."""
        chunks = [_to_chunk(c) for c in (chunks or [])]
        return await self._qa_pair(question, chunks, mode="qa",
                                   facet="legacy", min_words=12)

    async def synthesize_compare(self, question: str, chunks):
        """v2 grounded comparisons: 'Compare X and Y' questions enumerated
        ONLY where both names co-occur in the anchor chunk (driver
        _compare_rows), so the alternatives are grounded by construction.
        Returns ``(pair, reason)``."""
        chunks = [_to_chunk(c) for c in (chunks or [])]
        return await self._qa_pair(question, chunks, mode="qa",
                                   facet="compare", min_words=15)

    async def synthesize_avatar(self, question: str, chunks):
        """Avatar corpus: first-person persona pair over summary-family chunks.
        Renders through BrainMode.AVATAR (avatar.j2) — the same template the
        router serves for persona queries — so train prompt == serve prompt (P8)."""
        from src.brain.mode_router import BrainMode
        chunks = [_to_chunk(c) for c in (chunks or [])]
        return await self._qa_pair(question, chunks, mode="avatar",
                                   facet="avatar", tol_floor=2,
                                   brain_mode=BrainMode.AVATAR)

    async def synthesize_letter(self, job: Dict[str, Any], top_k: int = 6):
        """Letter facet (spec §3.1/§3.3): prose pair on the cover_letter.j2 serving path.
        Returns ``(pair, reason)`` — reason None on success, else the drop cause
        (2026-08-28 smoke: 4/4 letters died silently; every None path now named)."""
        from src.brain.mode_router import BrainMode
        from src.brain.prompt_builder import build_prompt
        from src.brain.retriever import BrainRetriever
        from src.brain.validator import extract_entities
        retriever = self.retriever or BrainRetriever()
        jd = job["jd"]
        chunks = retriever.retrieve(jd[:200], BrainMode.TAILORING, top_k=top_k, job_desc=jd)
        if not chunks:
            return None, "no_chunks"
        prompt = build_prompt("Write a cover letter for this job.", BrainMode.TAILORING,
                              chunks, job_desc=jd, facet="letter")
        try:
            answer = await self._call_teacher(prompt, json_mode=False)
        except Exception as e:
            logger.warning("Teacher call failed for cover letter %s: %s", job.get("job_id"), e)
            return None, f"teacher_fail: {str(e)[:160]}"
        words = len(answer.split())
        if not (250 <= words <= 350):
            return None, f"length_band: {words} words outside 250-350"  # §3.3, hard at synth
        pool = set()
        for c in chunks:
            pool |= extract_entities(c.content)
        ungrounded = extract_entities(answer) - pool
        if len(ungrounded) > max(1, len(extract_entities(answer)) // 5):
            return None, f"entity_gate: {sorted(ungrounded)[:5]}"
        return {
            "messages": [
                {"role": "system", "content": "You are Alex Rivera writing a cover letter draft."},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer},
            ],
            "metadata": {"mode": "tailoring", "facet": "cover_letter",
                         "job_id": job.get("job_id"),
                         "chunk_ids": [getattr(c, "id", None) for c in chunks],
                         "synthesis_model": self.teacher_model},
        }, None


_SYSTEM_TAILOR = "You are a resume tailoring assistant for Alex Rivera. You output ONE section plan as JSON only."
