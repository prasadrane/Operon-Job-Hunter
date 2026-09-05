"""G1 synth driver: JD pool -> section-tagged tailor pairs + three qa facets
(behavioral x story, grounded factual, avatar -  spec §3.4, plan Rev 1.3).

Train format == serve format (P8): pairs are built by Synthesizer facet
methods on the real retrieval + serving-prompt path.

Throughput (live pilot 2026-08-27: ~49 s/teacher call sequential -> ~30 h full
build): facet jobs run concurrently under asyncio.Semaphore(4).
Crash-safety (round 2): every completed unit appends + fsyncs its pairs/rejects
to the out-dir JSONLs IMMEDIATELY, so a mid-session death loses at most the
in-flight calls, not the whole run. File order = COMPLETION order (not task
order) -  accepted: resume skips by job_id/wid and the final dedup rewrites the
files, so byte order is not a contract. Resume: existing tailor_pairs.jsonl /
qa_pairs.jsonl are read on start; tailor/letter jobs whose job_id already has a
pair and qa work items whose wid already has a pair are skipped (auto-detected
with a warning, or explicit --append).
"""
from __future__ import annotations

import argparse, asyncio, json, os, sys, threading
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).parent))
from build_frozen_eval import _load_jobs, _stratified_sample, AUTHORED_BEHAVIORAL  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_held_out(eval_dir: Path) -> Set:
    p = eval_dir / "tailor_frozen.jsonl"
    if not p.exists():
        print(f"WARNING: no frozen tailor set at {p} -  held-out exclusion disabled")
        return set()
    return {json.loads(l)["job_id"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}


QA_FACETS = ("behavioral", "factual", "avatar", "legacy", "compare")

# v2.4: minimum chunk substance (words) for an ANCHOR -  below this the
# teacher has nothing to honestly say (name-node probes 2026-08-28).
RICH_MIN = 12
# spec §3.4 qa mix (plan Rev 1.3 + F5 + grounded-volume v2)

LEGACY_PAIRS = Path("data/brain/training_pairs.jsonl")  # v1 corpus re-synthesized grounded (§3.4)

# v2 grounding vocab: capitalized query entities that are sentence furniture,
# not facts to ground (probe 2026-08-28: 338/359 legacy questions fully
# groundable in chunk text -  the failures were RRF ranking luck, not data).
_QUERY_STOP = {"what", "which", "how", "can", "could", "do", "does", "tell",
               "describe", "walk", "explain", "many", "is", "are", "was",
               "were", "your", "you", "have", "had", "did", "any", "i", "the",
               "a", "an", "of", "in", "on", "with", "to", "for", "and", "or",
               "but", "about", "me", "my", "we", "they", "it", "this", "that",
               "compare", "versus"}


def _query_entities(question: str) -> Set[str]:
    import re
    # v2.3: no trailing \b (kills "C#" before "?"); token must end alnum/#.
    return {m.lower().rstrip(".,;:")
            for m in re.findall(r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9+#.\-]*[A-Za-z0-9#]", question)} \
       - _QUERY_STOP


def _legacy_qa_rows(chunks: List[Dict]) -> List[Dict]:
    """Spec §3.4 remainder: the existing 386 legacy pairs re-synthesized into
    the grounded format (v2: anchored on the FIRST chunk whose text contains
    every capitalized query entity -  deterministic grounding by construction,
    not serve-retrieval luck; ungroundable questions are SKIPPED at plan time
    so no teacher call is burned on a refusal)."""
    if not LEGACY_PAIRS.exists():
        print(f"WARNING: no legacy pairs at {LEGACY_PAIRS} -  F5 remainder skipped")
        return []
    index_by_id = {c.get("id", ""): c for c in chunks}
    tok_map: Dict[str, List[str]] = {}
    for c in chunks:
        # v2.3: {1,} so 2-char names ("C#", "AI") are indexable tokens.
        for m in __import__("re").findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}",
                                          c.get("content") or ""):
            tok_map.setdefault(m.lower().rstrip(".,;:"), []).append(c.get("id", ""))
    seen, rows, skipped = set(), [], 0
    for r in _read_jsonl(LEGACY_PAIRS):
        msgs = {m.get("role"): (m.get("content") or "").strip()
                for m in r.get("messages", [])}
        q = msgs.get("user", "")
        if not q or q in seen:
            continue
        seen.add(q)
        ents = _query_entities(q)
        if ents:
            common = None
            for e in sorted(ents):
                ids = set(tok_map.get(e) or [])
                common = ids if common is None else (common & ids)
                if not common:
                    break
            if not common:
                skipped += 1
                continue
            # v2.3: richest common chunk; v2.4: must clear RICH_MIN words - 
            # a name-node proving the token still supports no honest answer.
            anchor = max((c.get("id", "") for c in chunks if c.get("id", "") in common),
                         key=lambda cid: len((index_by_id[cid].get("content") or "").split()))
            if len((index_by_id[anchor].get("content") or "").split()) < RICH_MIN:
                skipped += 1
                continue
            rows.append({"facet": "legacy", "question": q, "chunk_ids": [anchor],
                         "wid": f"legacy:{q}"})
        else:
            rows.append({"facet": "legacy", "question": q, "chunk_ids": [],
                         "wid": f"legacy:{q}"})
    print(f"legacy plan: {len(rows)} anchored, {skipped} ungroundable skipped (no teacher burn)")
    return rows


def _compare_rows(chunks: List[Dict]) -> List[Dict]:
    """v2 grounded volume: 'Compare X and Y' ONLY where both tech names occur
    in one chunk (anchor-by-construction grounding -  the post-fix smoke showed
    template-level 'Compare {name} to alternatives' refusal-drowning on nodes
    with no alternative present). One pair per chunk, deterministic order."""
    import re
    techs = sorted({(c.get("metadata") or {}).get("name") for c in chunks
                    if c.get("type") == "graph_node"
                    and (c.get("metadata") or {}).get("node_type") == "Technology"
                    and (c.get("metadata") or {}).get("name")})
    # v2.1: nested product names (".NET"/".NET Core", "AWS"/"AWS Lambda")
    # are not comparables -  co-occurrence is a substring artifact.
    def _collide(a, b):
        na, nb = a.lower(), b.lower()
        return na in nb or nb in na
    pat = {t: re.compile(r"\b" + re.escape(t) + r"\b", re.I) for t in techs}
    rows, seen = [], set()
    for c in chunks:
        txt = c.get("content") or ""
        if len(txt.split()) < RICH_MIN:  # v2.4: name-drop fragments can't
            continue                      # support an honest "how featured"
        hits = sorted(t for t in techs if pat[t].search(txt))
        # <=3 non-colliding pairs per chunk (first pairs in sorted order),
        # global pair dedup -  each (x,y) question asked once, anchored on the
        # chunk that co-mentions them.
        made = 0
        for i, x in enumerate(hits[:8]):
            for y in hits[i + 1:8]:
                if made >= 3 or len(rows) >= 800:  # volume cap for G1 qa margin
                    break
                if _collide(x, y) or (x, y) in seen:
                    continue
                seen.add((x, y))
                made += 1
                q = f"How have {x} and {y} featured in your work?"
                rows.append({"facet": "compare", "question": q,
                             "chunk_ids": [c.get("id", "")],
                             "wid": f"compare:{c.get('id','')}:{x}:{y}"})
            if made >= 3 or len(rows) >= 800:
                break
    return rows


def qa_facet_jobs() -> List[Dict]:
    """Deterministic G1 qa work plan over the MASTER_RESUME chunk pool
    (v2.4: every row anchored on >=RICH_MIN-word chunks that actually mention
    its subject -  honest-teacher smokes proved thin/abstract anchors only
    produce refusals or fabrications). behavioral = 1 fit row per AUTHORED
    archetype (serve-retrieved whole stories at run time); factual = per-
    Technology mention rows ("Tell me about your work with X.", router->avatar
    first-person) + bank templates over rich non-Technology nodes; compare =
    co-occurring tech pairs inside rich chunks; avatar = AVATAR_QUESTIONS x
    persona chunks; legacy = spec §3.4 386 re-synth, richest mentioning chunk.
    Rows are {"facet", "question", "chunk_ids", "wid"} -  wid is the stable
    resume identity written into pair metadata for crash-safe resume."""
    from src.brain.synthesizer import (AVATAR_QUESTIONS, DEFAULT_FACT_QUESTIONS,
                                       FACT_QUESTIONS, SYNTHESIZABLE_NODE_TYPES)
    from src.brain.validator import MASTER_RESUME_JSONL, _load_chunks
    chunks = _load_chunks(MASTER_RESUME_JSONL)
    jobs: List[Dict] = []

    def _row(facet, question, chunk_id):
        return {"facet": facet, "question": question,
                "chunk_ids": [chunk_id], "wid": f"{facet}:{chunk_id}:{question}"}

    # v2 behavioral: one row per archetype question; the anchor chunks are the
    # SERVE-retrieved top-3 STAR-family nodes for that question (fit by
    # construction -  the forced 18x18 grid drowned in honest refusals).
    for i, q in enumerate(AUTHORED_BEHAVIORAL):
        jobs.append({"facet": "behavioral", "question": q, "chunk_ids": [],
                     "wid": f"behavioral:{i:02d}"})
    # v2.4 factual: every anchor must be RICH (>=RICH_MIN words) and must
    # actually MENTION the subject. Thin name-nodes (OAuth2/Lambda probe:
    # content=1 word) were anchored + random-adjacent -> teacher either
    # refused honestly or fabricated. Technologies now get one question per
    # top-3 richest chunks that mention them ("Tell me about your work with
    # X." -> router AVATAR first-person, same mechanism as behavioral fit).
    import re as _re
    words = lambda c: (c.get("content") or "").split()
    rich_chunks = [c for c in chunks if len(words(c)) >= RICH_MIN]
    tech_names = sorted({(c.get("metadata") or {}).get("name") for c in chunks
                         if c.get("type") == "graph_node"
                         and (c.get("metadata") or {}).get("node_type") == "Technology"
                         and (c.get("metadata") or {}).get("name")})
    for name in tech_names:
        pat = _re.compile(r"\b" + _re.escape(name) + r"\b", _re.I)
        mentions = sorted((c for c in rich_chunks if pat.search(c.get("content") or "")),
                          key=lambda c: -len(words(c)))[:3]
        if not mentions:
            continue
        q = f"Tell me about your work with {name}."
        jobs.append({"facet": "factual", "question": q,
                     "chunk_ids": [m.get("id", "") for m in mentions],
                     "wid": f"factual:mention:{name}"})
    for c in chunks:
        if c.get("type") != "graph_node":
            continue
        md = c.get("metadata") or {}
        nt = md.get("node_type", "")
        if nt not in SYNTHESIZABLE_NODE_TYPES and nt not in FACT_QUESTIONS:
            continue
        if nt == "Technology":
            continue  # v2.4: handled by mention enumeration above
        if len(words(c)) < RICH_MIN:
            continue  # every remaining anchor is rich or nothing
        name = str(md.get("name") or c.get("content", ""))
        for tpl in FACT_QUESTIONS.get(nt) or DEFAULT_FACT_QUESTIONS:
            if "ompare" in tpl:
                continue  # v2: comparisons live only in co-occurrence rows
            jobs.append(_row("factual", tpl.format(name=name), c.get("id", "")))
    jobs.extend(_compare_rows(chunks))  # v2 grounded comparisons
    persona = [c for c in chunks
               if c.get("type") in ("summary", "summary_variant")
               or (c.get("type") == "graph_node"
                   and (c.get("metadata") or {}).get("node_type") == "Role")]
    for q in AVATAR_QUESTIONS:
        for p in persona:
            jobs.append(_row("avatar", q, p.get("id", "")))
    jobs.extend(_legacy_qa_rows(chunks))  # F5: spec §3.4 grounded re-synth (v2 anchored)
    return jobs


SYNTH_CONCURRENCY = 4  # teacher calls in flight (rate-limit-safe, pilot-measured)

# G1 gates. qa amended 2026-08-28 (user ruling, see notes.md): 900 -> 400 - 
# honest-grounded capacity of MASTER_RESUME measured ~718 rows @ ~45-72%
# acceptance across v2.2-v2.4 smokes; refusals are correct teacher behavior;
# v1 trained on 386 pairs; spec §3.4 defers bank growth to flywheel rounds.
G1_TAILOR_GATE = 1600
G1_QA_GATE = 400


def _read_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


class _Sink:
    """Crash-safe JSONL appender: each row is written, flushed AND fsynced
    under a lock. asyncio is single-threaded but teacher calls run on executor
    threads and the sink is called from task continuations -  the lock keeps
    line appends atomic regardless."""

    def __init__(self, out_dir: Path):
        self._lock = threading.Lock()
        self.tailor_path = Path(out_dir) / "tailor_pairs.jsonl"
        self.qa_path = Path(out_dir) / "qa_pairs.jsonl"
        self.rejects_path = Path(out_dir) / "rejects.jsonl"
        self.pairs_written = 0
        self.rejects_written = 0

    def _append(self, path: Path, row: Dict):
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def pair(self, pair: Dict):
        path = self.qa_path if (pair.get("metadata") or {}).get(
            "facet") in QA_FACETS else self.tailor_path
        self._append(path, pair)
        self.pairs_written += 1

    def reject(self, row: Dict):
        self._append(self.rejects_path, row)
        self.rejects_written += 1


def _dedupe_in_place(path: Path) -> int:
    """Embedding-dedupe a pairs file (whole corpus, so cross-run near-dupes
    are caught too) and atomically rewrite it. Returns rows removed."""
    rows = _read_jsonl(path)
    if not rows:
        return 0
    from src.brain.dedup import deduplicate_pairs
    kept = deduplicate_pairs(rows)
    removed = len(rows) - len(kept)
    if removed:
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for row in kept:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    return removed


def _cap_per_facet(qa_rows: List[Dict], cap: int) -> List[Dict]:
    """Smoke aid: stride-sample `cap` jobs per facet -  the first N rows of a
    facet pile up on ONE anchor (all templates of one node, one question x
    the first stories), which biases acceptance measurement. Striding takes
    evenly spaced rows across the facet's whole anchor pool."""
    by_facet: Dict[str, List[Dict]] = {}
    for w in qa_rows:
        by_facet.setdefault(w["facet"], []).append(w)
    kept = []
    for rows in by_facet.values():
        n = min(cap, len(rows))
        stride = max(1, len(rows) // n)
        kept.extend(rows[i * stride] for i in range(n))
    return kept


async def _run_synth(jobs: List[Dict], out_dir: Path,
                     skip_wids: Optional[Set] = None,
                     qa_cap: Optional[int] = None) -> Dict:
    """Run all facet work concurrently (Semaphore(4)) with INCREMENTAL
    persistence: each completed unit appends+fsyncs its pairs and reject rows
    to the out-dir JSONLs before the next await, so a mid-session crash keeps
    everything already done (file order = completion order; resume skips by
    job_id/wid). Teacher-error containment lives in the Synthesizer methods;
    a failed unit produces reject rows only. An unexpected task exception is
    sunk as a driver_exception reject instead of killing the gather. Final
    step: corpus-wide dedup rewrite of both pair files.
    Returns stats: {pairs_written, rejects_written, dedup_removed}."""
    done_wids = set(skip_wids or ())
    sem = asyncio.Semaphore(SYNTH_CONCURRENCY)
    sink = _Sink(out_dir)
    from src.brain.synthesizer import Synthesizer
    syn = Synthesizer()
    from src.brain.retriever import BrainRetriever, RetrievedChunk
    from src.brain.mode_router import BrainMode
    from src.brain.validator import MASTER_RESUME_JSONL, _load_chunks
    retriever = BrainRetriever()
    index = {c.get("id"): c for c in _load_chunks(MASTER_RESUME_JSONL)}

    def _extras(query: str, anchor_id: str, taken: Set[str]) -> List:
        # v2.3: query = ANCHOR text (question words pollute RRF toward generic
        # nodes) and drop sub-5-word chunks (bare name-nodes add no evidence).
        return [c for c in retriever.retrieve(query[:120], BrainMode.QA, top_k=4)
                if c.id != anchor_id and c.id not in taken
                and len((c.content or "").split()) >= 5][:2]

    async def _tailor_task(job):
        async with sem:
            pairs, reject_details = await syn.synthesize_tailor_sections(job)
        for p in pairs:
            sink.pair(p)
        # reject_details rows carry {"job_id","section","reason"} (spec §3.2 flywheel)
        for d in reject_details:
            sink.reject({"facet": "tailor_resume", **d})

    async def _qa_task(job):
        facet, q = job["facet"], job["question"]
        # legacy rows retrieve per-unit (no fixed anchor); every other facet
        # anchors on one chunk from the plan.
        anchors = [RetrievedChunk(id=index[i].get("id", ""),
                                  content=index[i].get("content", ""), score=1.0,
                                  chunk_type=index[i].get("type", "unknown"),
                                  metadata=index[i].get("metadata") or {})
                   for i in job["chunk_ids"] if i in index]
        STAR_TYPES = {"story", "STAR_Story", "Project", "Result", "Action",
                      "Task", "Situation"}
        # v2.1: whole-story chunks carry enough situation+action for STAR
        # prose; Result/Action nodes are fragments the teacher honestly
        # refuses to expand into a narrative.
        WHOLE_STORY = {"story", "STAR_Story"}
        taken = {a.id for a in anchors}
        if not anchors and facet not in ("legacy", "behavioral"):
            sink.reject({"facet": facet, "question": q,
                         "chunk_ids": job["chunk_ids"], "reason": "no_chunks"})
            return
        async with sem:
            if facet == "behavioral":
                # v2: anchor = top-3 serve-retrieved STAR-family chunks
                found = anchors or retriever.retrieve(q, BrainMode.AVATAR, top_k=8)
                chunks = ([c for c in found if c.chunk_type in WHOLE_STORY]
                          or [c for c in found if c.chunk_type in STAR_TYPES])[:3]
                if not chunks:
                    sink.reject({"facet": facet, "question": q,
                                 "chunk_ids": [], "reason": "no_chunks"})
                    return
                pair, reason = await syn.synthesize_behavioral(q, chunks)
            elif facet == "factual":
                # v2.4: multi-anchor rows (mention enumeration) ground on the
                # rich mentioning chunks; retrieved extras only for single-
                # anchor bank rows.
                extras = (anchors[1:] + _extras(anchors[0].content, anchors[0].id, taken)
                          if len(anchors) > 1 else
                          _extras(anchors[0].content, anchors[0].id, taken))
                pair, reason = await syn.synthesize_fact_node(anchors[0], extras, question=q)
            elif facet == "compare":
                chunks = anchors + _extras(anchors[0].content, anchors[0].id, taken)
                pair, reason = await syn.synthesize_compare(q, chunks)
            elif facet == "legacy":
                # v2: plan-time entity-anchored chunk + context extras; rows
                # without query entities fall back to serve retrieval (F5).
                chunks = anchors or retriever.retrieve(q, BrainMode.QA, top_k=3)
                pair, reason = await syn.synthesize_legacy(q, chunks)
            else:  # avatar
                chunks = anchors + _extras(q, anchors[0].id, taken)
                pair, reason = await syn.synthesize_avatar(q, chunks)
        if pair:
            pair["metadata"]["wid"] = job.get("wid")  # resume identity
            sink.pair(pair)
        else:
            # reason returned per call (F2) -  no shared instance state to mask
            sink.reject({"facet": facet, "question": q, "chunk_ids": job["chunk_ids"],
                         "reason": reason or "ungrounded"})

    async def _letter_task(job):
        async with sem:
            pair, reason = await syn.synthesize_letter(job)
        if pair:
            sink.pair(pair)
        else:  # named drop cause (length_band / entity_gate / no_chunks / teacher_fail)
            sink.reject({"facet": "cover_letter", "job_id": job.get("job_id"),
                         "reason": (reason or "ungrounded_or_no_chunks").split(":")[0],
                         "detail": [(reason or "")[:200]]})

    qa_rows = [w for w in qa_facet_jobs() if w.get("wid") not in done_wids]
    if qa_cap is not None:
        if qa_cap == 0:  # explicit smoke switch: no qa calls at all
            qa_rows = []
        else:
            qa_rows = _cap_per_facet(qa_rows, qa_cap)
    tasks = ([_tailor_task(j) for j in jobs] + [_qa_task(w) for w in qa_rows]
             + [_letter_task(j) for j in jobs[:300]])  # spec §3.1: ~300 letter pairs
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, BaseException):  # containment: never lose the run to one unit
            sink.reject({"facet": "unknown",
                         "reason": f"driver_exception: {type(r).__name__}: {r}"})

    dedup_removed = {"tailor": _dedupe_in_place(sink.tailor_path),
                     "qa": _dedupe_in_place(sink.qa_path)}
    return {"pairs_written": sink.pairs_written,
            "rejects_written": sink.rejects_written,
            "dedup_removed": dedup_removed}


def build(db_path: Path, out_dir: Path, jd_limit: int, seed: int,
          held_out_job_ids: Set, append: bool = False,
          qa_cap: Optional[int] = None, allow_held_out: bool = False) -> Dict:
    jobs = _load_jobs(db_path)
    synth_pool = _stratified_sample([j for j in jobs], jd_limit, seed)
    if allow_held_out:
        # Smoke-only escape hatch: the frozen set covers the top strata, so
        # every small stratified sample lands 100% held-out (observed at
        # jd_limit 2/4/8/12/30). NEVER use for the real build -  its pairs
        # would teach the model its own eval answers.
        print("WARNING: held-out exclusion DISABLED (smoke-only flag)")
        excluded = 0
    else:
        excluded = sum(1 for j in synth_pool if j["job_id"] in held_out_job_ids)
        synth_pool = [j for j in synth_pool if j["job_id"] not in held_out_job_ids]
    out_dir.mkdir(parents=True, exist_ok=True)
    t_file, q_file = out_dir / "tailor_pairs.jsonl", out_dir / "qa_pairs.jsonl"
    if not append and (t_file.exists() or q_file.exists()):
        print(f"WARNING: existing pair files in {out_dir} -  append/resume mode "
              f"(pass --append to silence, or clear the dir for a fresh build)")
        append = True
    # resume: skip work whose output is already on disk. tailor/letter skip by
    # job_id (both pair kinds carry it); qa skips by stable wid.
    old_tailor, old_qa = (_read_jsonl(t_file), _read_jsonl(q_file)) if append else ([], [])
    done_job_ids = {p.get("metadata", {}).get("job_id") for p in old_tailor} - {None}
    skip_wids = {p.get("metadata", {}).get("wid") for p in old_qa} - {None}
    synth_pool = [j for j in synth_pool if j["job_id"] not in done_job_ids]
    # _run_synth persists incrementally (append+fsync per completed unit);
    # report counts are derived from the FINAL files, not in-memory lists.
    stats = asyncio.run(_run_synth(synth_pool, out_dir=out_dir, skip_wids=skip_wids,
                                   qa_cap=qa_cap))
    final_tailor = _read_jsonl(t_file)  # resume sections + letters (G1 counts both)
    final_qa = _read_jsonl(q_file)
    final_rejects = _read_jsonl(out_dir / "rejects.jsonl")
    n_tailor, n_qa = len(final_tailor), len(final_qa)
    report = {"jd_pool": len(jobs), "synth_jds": len(synth_pool),
              "held_out_excluded": excluded,
              "resumed_from": {"tailor": len(old_tailor), "qa": len(old_qa)},
              "pairs_written": stats["pairs_written"],
              "tailor_pairs": n_tailor, "qa_pairs": n_qa,
              "rejects": len(final_rejects),
              "pairs_by_facet": dict(Counter(p["metadata"].get("facet")
                                             for p in final_tailor + final_qa)),
              "rejects_by_facet": dict(Counter(r.get("facet") for r in final_rejects)),
              "rejects_by_reason": dict(Counter(r.get("reason") for r in final_rejects)),
              "dedup_removed": stats["dedup_removed"]}
    (out_dir / "synth_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # G1 gates: tailor >=1600 (plan); qa amended 2026-08-28 (user ruling):
    # 900 -> 400. Measured honest-grounded capacity of MASTER_RESUME is
    # ~718 rows / ~45% acceptance (v2.2-v2.4 smokes) -  the refusal class is
    # CORRECT teacher behavior, and v1 itself trained on 386 pairs. Spec
    # §3.4 defers bank growth to flywheel rounds; qa bank expands post-G3.
    t_pass = "PASS" if n_tailor >= G1_TAILOR_GATE else "FAIL"
    q_pass = "PASS" if n_qa >= G1_QA_GATE else "FAIL"
    print(f"G1 tailor pairs: {n_tailor}={t_pass} (target >={G1_TAILOR_GATE}); G1 qa pairs: {n_qa}={q_pass} (target >={G1_QA_GATE}, amended from 900)")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/careergraph.db")
    ap.add_argument("--out-dir", default="data/brain/synth")
    ap.add_argument("--jd-limit", type=int, default=630)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--allow-held-out", action="store_true",
                    help="SMOKE ONLY: skip held-out exclusion (small samples land "
                         "100% inside the frozen set) -  never for the real build")
    ap.add_argument("--qa-cap", type=int, default=None,
                    help="smoke aid: cap planned qa jobs per facet, stride-sampled "
                         "(0 = skip qa entirely; omit for full v2 plan: behav 18 / "
                         "fact 504 / compare ~191 / avatar 90 / legacy ~336)")
    ap.add_argument("--append", action="store_true",
                    help="resume: append to existing pair files, skip jobs/wids already synthesized "
                         "(auto-detected with a warning when the out-dir files exist)")
    ap.add_argument("--dry-run", action="store_true",
                    help="pool stats + held-out exclusion only, no teacher calls")
    a = ap.parse_args()
    held = _load_held_out(Path("data/brain/eval"))
    if a.dry_run:
        jobs = _load_jobs(Path(a.db))
        pool = _stratified_sample(jobs, a.jd_limit, a.seed)
        excl = sum(1 for j in pool if j["job_id"] in held)
        print(json.dumps({"jd_pool": len(jobs), "sampled": len(pool),
                          "held_out_excluded": excl}, indent=2))
    else:
        build(Path(a.db), Path(a.out_dir), a.jd_limit, a.seed, held,
              append=a.append, qa_cap=a.qa_cap,
              allow_held_out=a.allow_held_out)
