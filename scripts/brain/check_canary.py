"""G4 canary: numeric revert triggers from telemetry (spec §7.3 O1)."""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from typing import Dict, List


def evaluate(records: List[Dict]) -> Dict[str, Dict]:
    """Each signal's denominator is the records that OBSERVE it (have the
    field). Zero observers -> N/A with value None -  never PASS on absent
    data (P7 producers add fields incrementally; blind telemetry must not
    read as an all-clear)."""
    def v(status, value, trigger):
        return {"status": status, "value": value, "trigger": trigger}

    def observers(field):
        return [r for r in records if field in r]

    integ_obs = observers("plan_integrity_violations")
    integrity = sum(r["plan_integrity_violations"] for r in integ_obs)
    fmt_obs = observers("format_fail")
    fmt_fail = (sum(1 for r in fmt_obs if r["format_fail"]) / len(fmt_obs)) if fmt_obs else None
    trunc_records = [r for r in records if "prompt_eval_count" in r and "num_ctx" in r]
    trunc = (sum(1 for r in trunc_records if r["prompt_eval_count"] >= r["num_ctx"]) / len(trunc_records)) if trunc_records else None
    fg_obs = observers("factguard_verdict")
    fg_fail = (sum(1 for r in fg_obs if r["factguard_verdict"] in ("fail", "invalid")) / len(fg_obs)) if fg_obs else None
    coll_obs = observers("reduce_collisions")
    half = max(1, len(coll_obs) // 2)
    coll_first = sum(r["reduce_collisions"] for r in coll_obs[:half])
    coll_second = sum(r["reduce_collisions"] for r in coll_obs[half:])

    return {
        "plan_integrity": v("N/A" if not integ_obs else ("ALERT" if integrity > 0 else "PASS"),
                            None if not integ_obs else integrity, ">0 -> investigate (gate promises 100%)"),
        "format_fail": v("N/A" if fmt_fail is None else ("ALERT" if fmt_fail > 0.05 else "PASS"),
                         None if fmt_fail is None else round(fmt_fail, 3), ">5% -> GBNF escalation"),
        "truncation": v("N/A" if trunc is None else ("ALERT" if trunc > 0.02 else "PASS"),
                        None if trunc is None else round(trunc, 3), ">2% -> num_ctx bump"),
        "factguard": v("N/A" if fg_fail is None else ("ALERT" if fg_fail > 0.10 else "PASS"),
                       None if fg_fail is None else round(fg_fail, 3), ">10% -> revert pointer to v1"),
        "reduce_collisions": v("N/A" if not coll_obs else ("WARN" if coll_second > coll_first else "PASS"),
                               None if not coll_obs else f"{coll_first}->{coll_second}",
                               "trending up -> retrieval dedup investigation"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--telemetry", default="data/brain/telemetry/brain_calls.jsonl")
    a = ap.parse_args()
    path = Path(a.telemetry)
    if not path.exists():
        print("PENDING: no telemetry file yet (P7 writes it on first brain call)")
        return 0
    records: List[Dict] = []
    malformed = 0
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            malformed += 1
            print(f"ERROR: malformed line {i}", file=sys.stderr)
    if malformed:
        print(f"note: {malformed} malformed line(s) skipped; verdicts from {len(records)} parseable records", file=sys.stderr)
    if not records:
        print("PENDING: telemetry file has no complete records yet")
        return 0
    verdicts = evaluate(records)
    alert = False
    for name, v in verdicts.items():
        print(f"{name:16s} {v['status']:6s} value={v['value']} ({v['trigger']})")
        alert = alert or v["status"] == "ALERT"
    return 1 if alert else 0


if __name__ == "__main__":
    raise SystemExit(main())
