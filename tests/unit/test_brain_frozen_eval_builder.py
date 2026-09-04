import importlib, json, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts/brain")))
builder = importlib.import_module("build_frozen_eval")


def _fixture_db(tmp_path: Path) -> Path:
    db = tmp_path / "careergraph.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE jobs (id INTEGER, title TEXT, company TEXT, description TEXT)")
    for i in range(40):
        title = ["Senior Backend Engineer", "Staff Data Engineer", "SRE"][i % 3]
        con.execute("INSERT INTO jobs VALUES (?,?,?,?)",
                    (i, title, f"Co{i % 7}", f"Job description body {i} " + "x" * 300))
    con.commit(); con.close()
    return db


def _fixture_suite(tmp_path: Path) -> Path:
    p = tmp_path / "eval_suite.json"
    qs = [{"id": f"q{i}", "query": f"question {i}", "mode": ["qa", "avatar", "tailoring"][i % 3]}
          for i in range(30)]
    p.write_text(json.dumps({"questions": qs}), encoding="utf-8")
    return p


def test_builder_deterministic_and_stratified(tmp_path):
    db, suite = _fixture_db(tmp_path), _fixture_suite(tmp_path)
    out = tmp_path / "eval"
    r1 = builder.build(db_path=db, suite_path=suite, out_dir=out, n_tailor=12, seed=42)
    r2 = builder.build(db_path=db, suite_path=suite, out_dir=out, n_tailor=12, seed=42)
    t = [json.loads(l) for l in (out / "tailor_frozen.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(t) == 12 and r1 == r2
    assert all(row["gold"] is None for row in t)
    titles = {row["title"] for row in t}
    assert len(titles) >= 2  # stratified across title clusters


def test_qa_composition_and_probes(tmp_path):
    db, suite = _fixture_db(tmp_path), _fixture_suite(tmp_path)
    out = tmp_path / "eval"
    builder.build(db_path=db, suite_path=suite, out_dir=out, n_tailor=8, seed=42)
    qa = [json.loads(l) for l in (out / "qa_frozen.jsonl").read_text(encoding="utf-8").splitlines()]
    probes = [q for q in qa if q["expected"] == "admit"]
    assert len(probes) == 12
    assert len(qa) == 55  # 18 + 18 + 7 + 12, reachable via authored top-up (B4)
    answered = [q for q in qa if q["expected"] == "answer"]
    assert {q["bucket"] for q in answered} == {"behavioral", "factual", "avatar"}
    from collections import Counter
    assert Counter(q["bucket"] for q in answered) == {"behavioral": 18, "factual": 18, "avatar": 7}


def test_manifest_hashes(tmp_path):
    db, suite = _fixture_db(tmp_path), _fixture_suite(tmp_path)
    out = tmp_path / "eval"
    builder.build(db_path=db, suite_path=suite, out_dir=out, n_tailor=8, seed=42)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert {"tailor_frozen.jsonl", "qa_frozen.jsonl"} <= set(manifest["files"])
    assert all(len(h) == 64 for h in manifest["files"].values())
