"""P6: one-time cloud 7-block gold run over the frozen tailor set (spec §4.1).

Gold rows feed the §4.2 recall@5 grader. Hash-logged; never re-run without
--force (gold is part of the frozen contract).
"""
from __future__ import annotations

import argparse, hashlib, importlib, json, sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _manifest_path(eval_dir: Path) -> Path:
    return eval_dir / "manifest.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_gold(frozen_path: Path, evaluator, limit: Optional[int],
                  dry_run: bool, force: bool = False) -> dict:
    rows = [json.loads(l) for l in frozen_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if any(r.get("gold") for r in rows) and not force:
        raise RuntimeError("gold already present — use --force to regenerate (hash contract!)")
    manifest_path = _manifest_path(frozen_path.parent)
    old_hashes = json.loads(manifest_path.read_text(encoding="utf-8")).get("files", {}) \
        if manifest_path.exists() else {}
    if dry_run:
        print(f"DRY RUN: would evaluate {min(limit or len(rows), len(rows))} JDs")
        return {"files": old_hashes, "old_hashes": old_hashes}
    JobPosting = importlib.import_module("src.core.models").JobPosting
    for row in rows[:limit] if limit else rows:
        job = JobPosting(id=str(row["job_id"]), title=row["title"],
                         company=row["company"], url="", description=row["jd"])
        res = evaluator.evaluate(job)
        # Real EvaluationResult (src/core/models.py): block_scores dict, no
        # `passed` field — derive it the same way the pipeline gates progression.
        block_b = (res.block_scores.get("block_b") or {})
        row["gold"] = {"fit_score": res.fit_score,
                       "passed": (not res.work_auth_blocker and not res.is_ghost_job
                                  and res.fit_score >= 72.0),
                       "matched_skills": block_b.get("matched_skills", []),
                       "missing_skills": block_b.get("missing_skills", [])}
    frozen_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
                           encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"files": {}}
    manifest["files"]["tailor_frozen.jsonl"] = _sha(frozen_path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"GOLD hash: tailor_frozen.jsonl sha256={manifest['files']['tailor_frozen.jsonl']}")
    return {"files": manifest["files"], "old_hashes": old_hashes}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", default="data/brain/eval")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    frozen = Path(a.eval_dir) / "tailor_frozen.jsonl"
    if a.dry_run:
        generate_gold(frozen, None, a.limit, dry_run=True)
    else:
        RubricEvaluator = importlib.import_module(
            "src.pipeline.2_evaluation.rubric_evaluator").RubricEvaluator
        generate_gold(frozen, RubricEvaluator(), a.limit, dry_run=False, force=a.force)
