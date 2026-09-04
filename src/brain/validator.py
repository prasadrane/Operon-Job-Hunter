"""Validate training pairs for schema correctness and fact grounding."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MAX_RESPONSE_WORDS = 800
MIN_RESPONSE_WORDS = 20
REQUIRED_ROLES = {"system", "user", "assistant"}


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def validate_training_pair(pair: Dict[str, Any]) -> ValidationResult:
    """Validate a single training pair for schema and content quality."""
    result = ValidationResult()
    messages = pair.get("messages", [])

    # Check required roles
    roles_present = {m.get("role") for m in messages}
    missing = REQUIRED_ROLES - roles_present
    if missing:
        result.is_valid = False
        result.errors.append(f"Missing roles: {missing}")
        return result

    # Check non-empty content
    for msg in messages:
        if not msg.get("content", "").strip():
            result.is_valid = False
            result.errors.append(f"Empty content for role: {msg.get('role')}")
            return result

    # Check assistant response length
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    if assistant_msgs:
        word_count = len(assistant_msgs[0]["content"].split())
        if word_count > MAX_RESPONSE_WORDS:
            result.is_valid = False
            result.errors.append(f"Response too long: {word_count} words (max {MAX_RESPONSE_WORDS})")
        elif word_count < MIN_RESPONSE_WORDS:
            result.warnings.append(f"Response short: {word_count} words (min {MIN_RESPONSE_WORDS})")

    return result


def validate_all(pairs: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[str]]:
    """Validate all pairs, return (valid_pairs, errors)."""
    valid = []
    errors = []
    for i, pair in enumerate(pairs):
        result = validate_training_pair(pair)
        if result.is_valid:
            valid.append(pair)
        else:
            errors.append(f"Pair {i}: {'; '.join(result.errors)}")
    return valid, errors


import json
import re
from dataclasses import dataclass, field as dc_field
from functools import lru_cache
from pathlib import Path

from src.brain.tailor_schema import TailorPlan


def master_resume_jsonl_path() -> Path:
    """Active profile's MASTER_RESUME.jsonl (PROFILE_DATA_DIR-aware)."""
    from src.core.config import get_settings
    return get_settings().master_resume_jsonl_path


MASTER_RESUME_JSONL = Path("data/MASTER_RESUME.jsonl")


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*|\d+(?:\.\d+)?%")

# M3 (spec §5.7 Rev 4.1): entity proxy = proper-noun stand-ins (capitalized
# tokens) + numbers/percents. Paraphrase verbs and connectives never count,
# so rewritten bullets are not punished for new wording; fabricated proper
# nouns and metrics still fail. Text-initial token skipped (sentence capital).
_STOPWORDS = {"the", "a", "an", "on", "in", "of", "to", "and", "or", "for",
              "with", "at", "by", "is", "are", "was", "were", "have",
              "has", "that", "this", "it", "as", "be", "from", "into", "via"}


_SENT_BREAK_CHARS = ".!?"


def extract_entities(text: str, skip_initial: bool = True) -> set:
    """Deterministic entity proxy: capitalized tokens + numeric/percent tokens.
    M3 (spec §5.7 Rev 4.1): "the text-initial token is skipped (sentence
    capital)" — a capital at a SENTENCE/line start is orthographic, not
    proper-noun evidence ("During the rollout, ..." must not make "during" an
    entity: paraphrase verbs and connectives never count). Fix wave F1
    (2026-08-28): the old code only skipped token 0 of the WHOLE text, so
    every mid-answer sentence-initial word became a pseudo-entity and prose
    facets died on the tolerance budget. skip_initial=False (gaps reverse-
    verification) still counts every capital. Numbers/percents always count."""
    out = set()
    text = text or ""
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(0)
        low = tok.lower().rstrip(".,;:")
        if len(low) <= 1 or low in _STOPWORDS:
            continue
        numeric = tok[-1] in "%0123456789"
        sent_initial = False
        if skip_initial:
            j = m.start() - 1
            while j >= 0 and text[j].isspace():
                j -= 1
            sent_initial = j < 0 or text[j] in _SENT_BREAK_CHARS
        if numeric or (tok[0].isupper() and not sent_initial):
            out.add(low)
    return out


def grounding_token_pool(text: str) -> set:
    """Grounding pool for qa-facet prose (fix wave F1b): extract_entities'
    sentence-initial skip is right on the ANSWER side (a capital may be
    orthographic) but wrong on the CHUNK side — an anchor chunk like
    "C# ASP.NET ..." loses its leading token to the skip, so a legitimately
    grounded mid-sentence "C#" in the answer reads as fabricated. Chunk text
    is evidence regardless of position: any raw alphanumeric token in the
    chunk is grounded. Fabrications still fail — by definition their tokens
    appear in no chunk."""
    out = {t.lower().rstrip(".,;:") for t in _TOKEN_RE.findall(text or "")
           if len(t) > 1}
    return out


def _load_chunks(path: Path):
    chunks = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    chunks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return chunks


def _employer_index(chunks) -> dict:
    """chunk/node id -> employer name. Built once per chunk-set identity."""
    by_graph_id = {}
    for c in chunks:
        if c.get("type") == "graph_node":
            gid = (c.get("metadata") or {}).get("graph_node_id") or (c.get("metadata") or {}).get("name")
            if gid:
                by_graph_id[str(gid).strip()] = c
    company_names = {str((c.get("metadata") or {}).get("name")).strip()
                     for c in chunks
                     if c.get("type") == "graph_node"
                     and (c.get("metadata") or {}).get("node_type") == "Company"}
    index = {}
    # direct metadata.company
    for c in chunks:
        comp = (c.get("metadata") or {}).get("company")
        if comp:
            index[c.get("id")] = comp
    # edge traversal: employer-owned relations pointing at stories/actions
    ownership_relations = {"LED_STORY", "HAS_ACTION", "CONTRIBUTED_TO", "EMPLOYED"}
    for c in chunks:
        if c.get("type") != "graph_edge":
            continue
        meta = c.get("metadata") or {}
        if meta.get("relation") not in ownership_relations:
            continue
        src = str(meta.get("source", "")).strip()
        if src in company_names:
            index[meta.get("target")] = src
    return index


_INDEX_CACHE = {}


def employer_of(chunk_id: str, chunks=None) -> Optional[str]:
    """Single employer-ownership resolver (spec P3): metadata.company, else
    ownership-relation edge to a Company node. None = unowned/unknown.

    Cache key is the chunk-set identity (B3: a single "explicit" slot would
    let test fixtures, synth corpora and eval sets contaminate each other
    within one process). The old endswith-suffix fallback is dropped — fuzzy
    id matching is a false-attribution risk.
    """
    key = id(chunks) if chunks is not None else str(master_resume_jsonl_path())
    if key not in _INDEX_CACHE:
        _INDEX_CACHE[key] = _employer_index(chunks if chunks is not None else _load_chunks(master_resume_jsonl_path()))
    return _INDEX_CACHE[key].get(chunk_id)


def corpus_entity_set() -> set:
    """Whole-corpus entity pool (lowercase extract_entities output) over
    MASTER_RESUME.jsonl — feeds the gaps reverse-verification in
    validate_tailor_output. Cached in _INDEX_CACHE under key "corpus"."""
    key = f"corpus:{master_resume_jsonl_path()}"
    if key not in _INDEX_CACHE:
        pool: set = set()
        for c in _load_chunks(master_resume_jsonl_path()):
            pool |= extract_entities(c.get("content", ""))
        _INDEX_CACHE[key] = pool
    return _INDEX_CACHE[key]


@dataclass
class TailorGateResult:
    plan: TailorPlan
    drops: List[str] = dc_field(default_factory=list)
    warnings: List[str] = dc_field(default_factory=list)
    confidence: float = 1.0


BOLD_MAX_WORDS = 5
BOLD_MAX_PHRASES = 2
BOLD_MAX_COVERAGE = 0.25


def slug_employer(name: str) -> str:
    """Canonical employer slug — single shared normalization (M7) for
    enumeration (Task 9), section-scope comparison here, and tests."""
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def _clean_bold(bold_terms: List[str], bullet_text: str, emphasized: set, jd_matched: set, metrics: set, warnings: List[str]) -> List[str]:
    kept = []
    allowed = emphasized | jd_matched | metrics
    for term in sorted(bold_terms, key=len, reverse=True):  # longest-first strip order
        if len(term.split()) > BOLD_MAX_WORDS or term.lower() not in bullet_text.lower():
            warnings.append(f"bold term rejected (granularity/substring): {term!r}")
            continue
        tokens = extract_entities(term, skip_initial=False)
        if not tokens or not any(t in allowed for t in tokens):
            warnings.append(f"bold term rejected (membership): {term!r}")
            continue
        coverage = sum(bullet_text.lower().count(t) * len(t) for t in [term.lower()]) / max(len(bullet_text), 1)
        if coverage > BOLD_MAX_COVERAGE or len(kept) >= BOLD_MAX_PHRASES:
            warnings.append(f"bold term rejected (coverage/count): {term!r}")
            continue
        kept.append(term)
    return kept


def resolve_source_chunk_id(source: str, chunk_ids: set) -> Optional[str]:
    """Resolve a raw model citation to an exact chunk ID in chunk_ids.

    Handles bracket prefixes (e.g. 'STAR_Story: story_1'), surrounding punctuation,
    and story number aliases ('story-6', 'story_6' -> 'Story 6 - ...').
    """
    if not source:
        return None
    s = source.strip()
    if s in chunk_ids:
        return s

    # Strip bracket or type prefix like 'STAR_Story: ' or 'Project: '
    if ":" in s:
        rest = s.split(":", 1)[1].strip()
        if rest in chunk_ids:
            return rest

    # Strip surrounding brackets/quotes
    trimmed = s.strip("[]'\"")
    if trimmed in chunk_ids:
        return trimmed
    if ":" in trimmed:
        rest = trimmed.split(":", 1)[1].strip()
        if rest in chunk_ids:
            return rest

    # Match story aliases: 'story-6', 'story_6', 'story 6', 'story-6-ai-intent...'
    m = re.match(r"^story[-_ ]?(\d+)\b", s, re.IGNORECASE)
    if m:
        num = m.group(1)
        for cid in chunk_ids:
            if re.match(rf"^(?:STAR_)?Story\s+{num}\b", cid, re.IGNORECASE) or \
               re.match(rf"^story_(?:story_)?{num}\b", cid, re.IGNORECASE):
                return cid

    # Case-insensitive direct match
    low = s.lower()
    for cid in chunk_ids:
        if cid.lower() == low:
            return cid

    return None


def validate_tailor_output(plan: TailorPlan, chunk_ids: set, chunk_entities: dict,
                           section: str, jd_entities: Optional[set] = None,
                           chunks=None,
                           corpus_entities: Optional[set] = None) -> TailorGateResult:
    """Serving gates for one section plan (spec §5.7). Mutates nothing; returns
    cleaned copy. B5: *jd_entities* feeds bold membership — without it the
    JD-aware-bold feature silently degrades to emphasized-only membership.

    *corpus_entities* and *chunk_entities* values must be lowercase
    extract_entities() output (call corpus_entity_set() for the corpus pool) —
    membership compares against extract_entities() of plan text, which is
    lowercased; any other casing silently disables the gaps check."""
    cleaned = plan.model_copy(deep=True)
    drops, warnings = [], []
    section_scope = section
    scope_employer = section.split("@", 1)[1] if "@" in section else None

    kept_bullets = []
    for b in cleaned.bullets:
        resolved_src = resolve_source_chunk_id(b.source, chunk_ids)
        if not resolved_src:
            drops.append(f"bullet dropped: unknown source {b.source!r}")
            continue
        b.source = resolved_src
        if scope_employer:
            owner = employer_of(b.source, chunks=chunks)
            if owner and slug_employer(owner) != scope_employer:
                drops.append(f"bullet dropped: source owned by {owner}, section is {section_scope}")
                continue
        src_ents = chunk_entities.get(b.source, set())
        bullet_ents = extract_entities(b.text)
        ungrounded = bullet_ents - src_ents
        if len(ungrounded) > max(1, len(bullet_ents) // 5):
            drops.append(f"bullet dropped: ungrounded entities {sorted(ungrounded)[:5]}")
            continue
        emphasized = {t.lower() for s in cleaned.stories for t in s.emphasize} \
            | {t.lower() for t in cleaned.skills_to_emphasize}
        b.bold = _clean_bold(b.bold, b.text, emphasized, jd_entities or set(),
                             {t for t in bullet_ents if "%" in t or t.replace(".", "").isdigit()},
                             warnings)
        kept_bullets.append(b)
    cleaned.bullets = kept_bullets

    kept_stories = []
    for s in cleaned.stories:
        resolved_id = resolve_source_chunk_id(s.id, chunk_ids)
        if not resolved_id:
            drops.append(f"story dropped: unknown id {s.id!r}")
            continue
        s.id = resolved_id
        kept_stories.append(s)
    cleaned.stories = kept_stories

    # gaps reverse-verification (spec §5.7 Phase 2): a claimed gap is only
    # real if no corpus chunk mentions the entity; caller supplies the
    # pool-wide entity set via corpus_entities.
    if corpus_entities is not None and cleaned.gaps:
        kept_gaps = []
        for gap in cleaned.gaps:
            if extract_entities(gap, skip_initial=False) & corpus_entities:
                warnings.append(f"gap rejected: not a real absence: {gap!r}")
            else:
                kept_gaps.append(gap)
        cleaned.gaps = kept_gaps

    mention = extract_entities(" ".join([b.text for b in cleaned.bullets]
                                        + [t for s in cleaned.stories for t in s.emphasize]))
    for skill in cleaned.skills_to_emphasize:
        if not extract_entities(skill) & mention:
            warnings.append(f"plan consistency: emphasized skill {skill!r} appears nowhere")

    confidence = max(0.0, 1.0 - 0.2 * len(drops) - 0.05 * len(warnings))
    return TailorGateResult(plan=cleaned, drops=drops, warnings=warnings, confidence=confidence)


def plan_to_prose(plan: TailorPlan) -> str:
    """Deterministic plan -> prose adapter (spec §6 / P1 QAGenerator)."""
    lines = []
    if plan.skills_to_emphasize:
        lines.append("Emphasize: " + ", ".join(plan.skills_to_emphasize) + ".")
    for s in plan.stories:
        lines.append(f"Story {s.id}: {s.why}" if s.why else f"Story {s.id}.")
    for b in plan.bullets:
        lines.append("- " + b.text)
    if plan.gaps:
        lines.append("Gaps: " + "; ".join(plan.gaps))
    return "\n".join(lines)
