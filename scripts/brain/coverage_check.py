"""Offline tailor-section retrieval coverage check (zero teacher calls).

Answers the question the killed full run asked expensively: after the v2.5
retrieval fix (query = JD text, top_k=10), does every enumerated section of
every synth-pool JD retrieve >=1 chunk (scope-filtered for employer sections)?
no_chunks at synth time costs a teacher call only per section that reaches
the teacher; a section with zero chunks is rejected BEFORE any call, so
coverage measured here predicts the run's no_chunks rate exactly.

Usage: python scripts/brain/coverage_check.py [--jd-limit 630] [--seed 42]
"""
from __future__ import annotations

import argparse, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_frozen_eval import _load_jobs, _stratified_sample  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main(jd_limit: int, seed: int) -> None:
    from scripts.brain.synth_pairs import _load_held_out
    from src.brain.inference import enumerate_sections
    from src.brain.mode_router import BrainMode
    from src.brain.retriever import BrainRetriever
    from src.brain.validator import employer_of, slug_employer

    held = _load_held_out(Path("data/brain/eval"))
    jobs = [j for j in _stratified_sample(_load_jobs(Path("data/careergraph.db")),
                                          jd_limit, seed) if j["job_id"] not in held]
    ret = BrainRetriever()
    covered = Counter()
    total = Counter()
    jobs_zero_sections = 0
    for j in jobs:
        jd = j["jd"]
        found_any = False
        for section in enumerate_sections():
            scope = section.split("@", 1)[1] if "@" in section else None
            chunks = ret.retrieve(jd[:300], BrainMode.TAILORING, top_k=10, job_desc=jd)
            if scope:
                chunks = [c for c in chunks
                          if slug_employer(employer_of(c.id) or "") == scope]
            kind = section.split("@")[0]
            total[kind] += 1
            if chunks:
                covered[kind] += 1
                found_any = True
        if not found_any:
            jobs_zero_sections += 1
    print(f"jobs in synth pool: {len(jobs)}; jobs with ZERO covered sections: {jobs_zero_sections}")
    for kind in sorted(total):
        print(f"{kind:<12} covered {covered[kind]:>4}/{total[kind]:>4} "
              f"({100*covered[kind]/max(1,total[kind]):.1f}%)")
    grand_c, grand_t = sum(covered.values()), sum(total.values())
    print(f"TOTAL covered {grand_c}/{grand_t} ({100*grand_c/max(1,grand_t):.1f}%)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--jd-limit", type=int, default=630)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    main(a.jd_limit, a.seed)
