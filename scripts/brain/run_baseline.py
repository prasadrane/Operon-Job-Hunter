# scripts/brain/run_baseline.py
"""P4: measure v1 baseline on frozen sets BEFORE the registry flip.

Writes data/brain/eval/baseline_v1.json. Requires Ollama running; exits
gracefully with a message otherwise. Note: the dict-scan bold baseline is
measured in Phase 3, immediately before the surgical_optimizer selection swap.
"""
from __future__ import annotations

import argparse, json, statistics, sys, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", default="data/brain/eval")
    ap.add_argument("--out", default="data/brain/eval/baseline_v1.json")
    ap.add_argument("--limit-qa", type=int, default=55)
    ap.add_argument("--limit-tailor", type=int, default=25)
    a = ap.parse_args()

    from src.brain.inference import BrainInference
    from src.brain.model_registry import get_model_registry

    brain = BrainInference()
    if not brain.ollama.is_available():
        print("Ollama not running -  start it and re-run. Baseline NOT written.")
        return 1

    registry_model = (get_model_registry().get_model_for_mode("qa") or {}).get("model_name")
    out = {"model": brain.ollama.model, "registry_active": registry_model,
           "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "qa": {}, "tailor": {}}

    eval_dir = Path(a.eval_dir)
    qa = [json.loads(l) for l in (eval_dir / "qa_frozen.jsonl").read_text(encoding="utf-8").splitlines()][:a.limit_qa]
    lat, conf, warns = [], [], 0
    for row in qa:
        t0 = time.time()
        res = brain.query(row["query"], mode=row["mode"])
        lat.append((time.time() - t0) * 1000)
        conf.append(res.confidence)
        warns += 1 if res.warnings else 0
    out["qa"] = {"n": len(qa), "latency_p50_ms": statistics.median(lat),
                 "latency_p95_ms": sorted(lat)[int(len(lat) * 0.95) - 1],
                 "avg_confidence": statistics.mean(conf),
                 "warning_rate": warns / max(len(qa), 1)}

    tailor = [json.loads(l) for l in (eval_dir / "tailor_frozen.jsonl").read_text(encoding="utf-8").splitlines()][:a.limit_tailor]
    lat, fmt_fail = [], 0
    from src.brain.tailor_schema import parse_tailor_plan
    for row in tailor:
        t0 = time.time()
        res = brain.query("Tailor this resume for the job", mode="tailoring", job_desc=row["jd"])
        lat.append((time.time() - t0) * 1000)
        if parse_tailor_plan(res.answer) is None:
            fmt_fail += 1
    out["tailor"] = {"n": len(tailor), "latency_p50_ms": statistics.median(lat),
                     "latency_p95_ms": sorted(lat)[int(len(lat) * 0.95) - 1],
                     "plan_parse_rate": 1 - fmt_fail / max(len(tailor), 1),
                     "note": "v1 emits prose; parse rate expected ~0 -  reference only"}

    Path(a.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
