import importlib, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "brain"))
canary = importlib.import_module("check_canary")


def test_clean_week_passes():
    recs = [{"mode": "tailoring", "factguard_verdict": "pass", "format_fail": False,
             "plan_integrity_violations": 0, "reduce_collisions": 0,
             "prompt_eval_count": 512, "num_ctx": 4096} for _ in range(50)]
    verdicts = canary.evaluate(recs)
    assert all(v["status"] == "PASS" for v in verdicts.values())


def test_plan_integrity_violation_alerts():
    recs = [{"mode": "tailoring", "factguard_verdict": "pass", "format_fail": False,
             "plan_integrity_violations": 1, "reduce_collisions": 0}]
    verdicts = canary.evaluate(recs)
    assert verdicts["plan_integrity"]["status"] == "ALERT"


def test_factguard_fail_rate_threshold():
    recs = ([{"mode": "qa", "factguard_verdict": "fail"}] * 3
            + [{"mode": "qa", "factguard_verdict": "pass"}] * 17)
    verdicts = canary.evaluate(recs)
    assert verdicts["factguard"]["status"] == "ALERT"  # 15% > 10%


def test_truncation_only_when_measured():
    recs = [{"mode": "tailoring", "factguard_verdict": "pass"}] * 10  # no prompt_eval_count
    verdicts = canary.evaluate(recs)
    assert verdicts["truncation"]["status"] == "N/A"


def test_unobserved_signals_are_na_not_pass():
    """Blind telemetry must never read as all-clear: a signal whose field is
    absent from every record is N/A with value None, not PASS on zero counts."""
    recs = [{"mode": "qa", "answer_len": 120} for _ in range(10)]  # no measured fields at all
    verdicts = canary.evaluate(recs)
    for name in ("plan_integrity", "format_fail", "factguard", "reduce_collisions", "truncation"):
        assert verdicts[name]["status"] == "N/A", name
        assert verdicts[name]["value"] is None, name


def test_partial_observation_uses_observed_denominator():
    """format_fail rate divides by the records that OBSERVE it, not all records."""
    recs = ([{"mode": "tailoring", "format_fail": True}]
            + [{"mode": "tailoring", "format_fail": False}] * 18
            + [{"mode": "tailoring"}] * 40)  # 40 records lack the field entirely
    verdicts = canary.evaluate(recs)
    assert verdicts["format_fail"]["status"] == "ALERT"  # 1/19 = 5.3% > 5% (vs 1/58 = PASS if blind)
    # factguard unobserved even though records exist -> N/A, not PASS
    assert verdicts["factguard"]["status"] == "N/A" and verdicts["factguard"]["value"] is None


def _run_main(tmp_path, monkeypatch, content):
    f = tmp_path / "brain_calls.jsonl"
    f.write_text(content, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_canary.py", "--telemetry", str(f)])
    return canary.main()


def test_torn_trailing_line_does_not_crash(tmp_path, monkeypatch):
    # live-append race: last line torn mid-write -> must be skipped, not traceback
    good = json.dumps({"mode": "qa", "factguard_verdict": "pass"})
    assert _run_main(tmp_path, monkeypatch, good + "\n" + '{"mode": "qa", "factg') == 0


def test_empty_file_is_pending(tmp_path, monkeypatch, capsys):
    assert _run_main(tmp_path, monkeypatch, "") == 0
    assert "PENDING" in capsys.readouterr().out


def test_alert_exits_one(tmp_path, monkeypatch):
    bad = json.dumps({"mode": "tailoring", "factguard_verdict": "pass",
                      "plan_integrity_violations": 1})
    assert _run_main(tmp_path, monkeypatch, bad + "\n") == 1
