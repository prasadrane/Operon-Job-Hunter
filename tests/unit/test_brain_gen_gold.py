import importlib, json, sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path("scripts/brain")))
gen = importlib.import_module("gen_gold")

from src.core.models import EvaluationResult


def _frozen(tmp_path):
    rows = [{"job_id": i, "title": "Engineer", "company": f"C{i}",
             "jd": f"Kafka AWS body {i}", "gold": None} for i in range(3)]
    p = tmp_path / "tailor_frozen.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def test_gold_written_and_hashes_updated(tmp_path):
    p = _frozen(tmp_path)
    fake_eval = MagicMock()
    # REAL EvaluationResult (not MagicMock) so field-name drift fails loudly.
    fake_eval.evaluate.return_value = EvaluationResult(
        fit_score=77.5,
        block_scores={"block_b": {"matched_skills": ["Kafka"],
                                  "missing_skills": ["Flink"]}})
    m = gen.generate_gold(p, evaluator=fake_eval, limit=2, dry_run=False)
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["gold"]["fit_score"] == 77.5
    assert rows[0]["gold"]["passed"] is True  # derived: >=72, no blockers
    assert rows[0]["gold"]["matched_skills"] == ["Kafka"]
    assert rows[0]["gold"]["missing_skills"] == ["Flink"]
    assert rows[2]["gold"] is None  # limit=2
    assert m["files"]["tailor_frozen.jsonl"] != m.get("old_hashes", {}).get("tailor_frozen.jsonl", "")


def test_gold_passed_derived_from_blockers_and_threshold(tmp_path):
    p = _frozen(tmp_path)
    fake_eval = MagicMock()
    fake_eval.evaluate.return_value = EvaluationResult(
        fit_score=90.0, is_ghost_job=True, block_scores={})
    gen.generate_gold(p, evaluator=fake_eval, limit=1, dry_run=False)
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["gold"]["passed"] is False  # ghost job vetoes fit_score
    assert rows[0]["gold"]["matched_skills"] == []

    p = _frozen(tmp_path)
    fake_eval.evaluate.return_value = EvaluationResult(
        fit_score=71.9, work_auth_blocker=False, block_scores={})
    gen.generate_gold(p, evaluator=fake_eval, limit=1, dry_run=False)
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["gold"]["passed"] is False  # below MIN_FIT_SCORE threshold


def test_refuses_existing_gold(tmp_path):
    p = _frozen(tmp_path)
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    rows[0]["gold"] = {"fit_score": 1.0}
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    import pytest
    with pytest.raises(RuntimeError):
        gen.generate_gold(p, evaluator=MagicMock(), limit=3, dry_run=False)
