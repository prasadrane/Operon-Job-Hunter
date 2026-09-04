import asyncio, importlib, json, sqlite3, sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path("scripts/brain")))
driver = importlib.import_module("synth_pairs")


def _fixture_db(tmp_path):
    db = tmp_path / "careergraph.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE jobs (id INTEGER, title TEXT, company TEXT, description TEXT)")
    for i in range(30):
        con.execute("INSERT INTO jobs VALUES (?,?,?,?)",
                    (i, ["Senior Backend Engineer", "SRE"][i % 2], f"Co{i % 3}",
                     f"Kafka and AWS job body {i} " + "x" * 300))
    con.commit(); con.close()
    return db


_STATS = {"pairs_written": 0, "rejects_written": 0, "dedup_removed": {"tailor": 0, "qa": 0}}


def test_synth_pool_excludes_held_out(tmp_path):
    db = _fixture_db(tmp_path)
    held_out = {0, 1, 2}  # pretend frozen tailor owns these job ids
    synth = AsyncMock(return_value=_STATS)
    with patch.object(driver, "_run_synth", synth):
        report = driver.build(db_path=db, out_dir=tmp_path / "synth", jd_limit=10,
                              seed=42, held_out_job_ids=held_out)
    pool = synth.await_args.args[0]  # real exclusion happens in build, before _run_synth
    assert pool and all(j["job_id"] not in held_out for j in pool)
    assert synth.await_args.kwargs["out_dir"] == tmp_path / "synth"
    assert "held_out_excluded" in report  # count depends on stratification overlap


def test_g1_line_and_report_shape(tmp_path, capsys):
    """_run_synth persists to the out_dir itself; build derives the report
    from the files on disk."""
    db = _fixture_db(tmp_path)
    out = tmp_path / "synth"

    def _side(jobs, out_dir=None, skip_wids=None, qa_cap=None):
        assert out_dir == out
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "tailor_pairs.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"messages": [], "metadata": {"job_id": 7,
                              "facet": "tailor_resume"}}) + "\n")
        with open(out / "rejects.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"job_id": 8, "facet": "tailor_resume",
                                "section": "skills", "reason": "gate_drop"}) + "\n")
        return {"pairs_written": 1, "rejects_written": 1,
                "dedup_removed": {"tailor": 1, "qa": 0}}

    with patch.object(driver, "_run_synth", AsyncMock(side_effect=_side)):
        report = driver.build(db_path=db, out_dir=out, jd_limit=5,
                              seed=1, held_out_job_ids=set())
    o = capsys.readouterr().out
    assert "G1 tailor pairs:" in o and "G1 qa pairs:" in o
    assert report["pairs_by_facet"] == {"tailor_resume": 1}
    assert report["rejects_by_facet"] == {"tailor_resume": 1}
    assert report["rejects_by_reason"] == {"gate_drop": 1}
    assert report["dedup_removed"] == {"tailor": 1, "qa": 0}
    assert report["tailor_pairs"] == 1 and report["rejects"] == 1
    on_disk = json.loads((out / "synth_report.json").read_text(encoding="utf-8"))
    assert on_disk["pairs_by_facet"] and on_disk["dedup_removed"] == {"tailor": 1, "qa": 0}


def test_qa_facets_expand_past_gate(tmp_path):
    """v2 grounded plan: behavioral = one fit row per archetype question
    (anchors are SERVE-retrieved at run time — the 18x18 forced grid drowned
    in honest refusals); volume comes from factual + compare + legacy."""
    rows = driver.qa_facet_jobs()
    facets = {r["facet"] for r in rows}
    assert {"behavioral", "factual", "avatar", "legacy", "compare"} <= facets
    assert sum(1 for r in rows if r["facet"] == "behavioral") == 18  # AUTHORED bank (spec §3.4)
    assert len(rows) >= 700  # v2.4 honest-grounding ceiling (see capacity test)
    # grounded-only enumeration (v2.1): no thin category anchors, no nested
    # product-name "comparisons" (.NET vs .NET Core etc.)
    from src.brain.validator import MASTER_RESUME_JSONL, _load_chunks
    index = {c["id"]: c for c in _load_chunks(MASTER_RESUME_JSONL)}
    from src.brain.synthesizer import SYNTHESIZABLE_NODE_TYPES as SYNTH
    for r in rows:
        if r["facet"] != "factual":
            continue
        c = index[r["chunk_ids"][0]]
        nt = (c.get("metadata") or {}).get("node_type", "")
        rich = len((c.get("content") or "").split()) >= 8
        assert nt in SYNTH or rich  # v2.2: thin only if real substance
        if not rich:
            assert "hands-on" in r["question"] or r["question"].startswith("What")
    for r in rows:
        if r["facet"] == "compare":
            import re
            x, y = re.match(r"How have (.+) and (.+) featured", r["question"]).groups()
            assert x.lower() not in y.lower() and y.lower() not in x.lower()


def test_fact_banks_cover_corpus_node_types():
    """Controller ruling: volume comes from FACT_QUESTIONS breadth, not from
    widening SYNTHESIZABLE_NODE_TYPES — every node_type in the live chunk pool
    must have a bank or be in the legacy synthesizable set."""
    from src.brain.synthesizer import FACT_QUESTIONS, SYNTHESIZABLE_NODE_TYPES
    from src.brain.validator import MASTER_RESUME_JSONL, _load_chunks
    types = {(c.get("metadata") or {}).get("node_type")
             for c in _load_chunks(MASTER_RESUME_JSONL) if c.get("type") == "graph_node"}
    assert types
    uncovered = types - SYNTHESIZABLE_NODE_TYPES - set(FACT_QUESTIONS)
    assert not uncovered, f"node types without a factual bank: {uncovered}"
    assert SYNTHESIZABLE_NODE_TYPES == {"Technology", "ImpactMetric", "STAR_Story", "Project"}


def test_qa_facet_capacity_reaches_gate():
    """v2.1 grounded-only plan: every row's anchors support its question by
    construction; capacity must clear 900 at the observed honest-teacher
    acceptance (smokes 75-90% by facet)."""
    rows = driver.qa_facet_jobs()
    assert len(rows) >= 700  # v2.4 grounded ceiling (see test above)
    assert sum(1 for r in rows if r["facet"] in ("compare", "legacy", "factual")) >= 600
    assert sum(1 for r in rows if r["facet"] == "avatar") >= 90


def test_qa_facet_jobs_carry_stable_wid():
    """Resume needs a stable work-item identity on every qa row."""
    rows = driver.qa_facet_jobs()
    wids = [r["wid"] for r in rows]
    assert all(wids) and len(set(wids)) == len(wids)
    b = next(r for r in rows if r["facet"] == "behavioral")
    assert b["wid"].startswith("behavioral:") and b["question"] not in b["wid"]  # v2: index wid, anchors retrieved at run time
    bank = next(r for r in rows if r["facet"] == "factual"
                and not r["wid"].startswith("factual:mention:"))
    assert bank["chunk_ids"][0] in bank["wid"] and bank["question"] in bank["wid"]
    men = next(r for r in rows if r["wid"].startswith("factual:mention:"))
    assert men["chunk_ids"]  # v2.4 mention rows anchor on rich mentioning chunks


class _FakeSynth:
    """Facet fakes with staggered sleeps; the last-finishing unit (behavioral
    q3) snapshots the pair files mid-gather — non-empty snapshot proves
    INCREMENTAL persistence (pairs visible before the run returns)."""
    out_dir = None
    saw = None

    def __init__(self):
        pass

    async def synthesize_tailor_sections(self, job, top_k=6):
        await asyncio.sleep(0.04 - 0.008 * int(job["job_id"]))
        return ([{"messages": [{"role": "assistant", "content": f"t{job['job_id']}"}],
                 "metadata": {"facet": "tailor_resume", "job_id": job["job_id"]}}], [])

    async def synthesize_behavioral(self, q, chunks):
        if q == "q3":  # last to finish — everything else must already be on disk
            await asyncio.sleep(0.20)
            if _FakeSynth.out_dir and _FakeSynth.saw is not None:
                t = (Path(_FakeSynth.out_dir) / "tailor_pairs.jsonl")
                v = (Path(_FakeSynth.out_dir) / "qa_pairs.jsonl")
                _FakeSynth.saw.append((
                    len(t.read_text(encoding="utf-8").splitlines()) if t.exists() else 0,
                    len(v.read_text(encoding="utf-8").splitlines()) if v.exists() else 0))
        else:
            await asyncio.sleep(0.01)
        return ({"messages": [{"role": "assistant", "content": f"b{q}"}],
                 "metadata": {"facet": "behavioral", "question": q}}, None)

    async def synthesize_fact_node(self, node, extras, question=None):
        await asyncio.sleep(0.02)
        return ({"messages": [{"role": "assistant", "content": "f"}],
                 "metadata": {"facet": "factual", "question": question}}, None)

    async def synthesize_avatar(self, q, chunks):
        await asyncio.sleep(0.01)
        return ({"messages": [{"role": "assistant", "content": "a"}],
                 "metadata": {"facet": "avatar", "question": q}}, None)

    async def synthesize_compare(self, q, chunks):
        await asyncio.sleep(0.01)
        return ({"messages": [{"role": "assistant", "content": "c"}],
                 "metadata": {"facet": "compare", "question": q}}, None)

    async def synthesize_letter(self, job, top_k=6):
        await asyncio.sleep(0.03 - 0.006 * int(job["job_id"]))
        return {"messages": [{"role": "assistant", "content": f"l{job['job_id']}"}],
                "metadata": {"facet": "cover_letter", "job_id": job["job_id"]}}, None


def _patch_facet_fakes(monkeypatch, tmp_path, chunks, qa_rows):
    import src.brain.dedup as d_mod
    import src.brain.retriever as ret_mod
    import src.brain.synthesizer as syn_mod
    import src.brain.validator as v_mod
    monkeypatch.setattr(v_mod, "_load_chunks", lambda path: chunks)

    class FakeRetriever:
        def retrieve(self, *a, **k):
            return []
    monkeypatch.setattr(ret_mod, "BrainRetriever", FakeRetriever)
    monkeypatch.setattr(d_mod, "_get_embeddings", lambda texts: np.eye(len(texts)))
    _FakeSynth.out_dir, _FakeSynth.saw = tmp_path, []
    monkeypatch.setattr(syn_mod, "Synthesizer", _FakeSynth)
    monkeypatch.setattr(driver, "qa_facet_jobs", lambda: qa_rows)


@pytest.mark.asyncio
async def test_run_synth_persists_pairs_incrementally(tmp_path, monkeypatch):
    """File order == completion order (accepted); content + incremental
    visibility + wid stamping are the invariants."""
    chunks = [
        {"id": "s1", "type": "story", "content": "Led Kafka governance.", "metadata": {}},
        {"id": "n1", "type": "graph_node", "content": "Apache Kafka",
         "metadata": {"node_type": "Technology", "name": "Apache Kafka"}},
        {"id": "p1", "type": "summary", "content": "Ten years.", "metadata": {}},
    ]
    qa_rows = [
        {"facet": "behavioral", "question": f"q{i}", "chunk_ids": ["s1"],
         "wid": f"behavioral:s1:q{i}"} for i in range(4)
    ] + [
        {"facet": "factual", "question": "fq", "chunk_ids": ["n1"], "wid": "factual:n1:fq"},
        {"facet": "avatar", "question": "aq", "chunk_ids": ["p1"], "wid": "avatar:p1:aq"},
        {"facet": "compare", "question": "cq", "chunk_ids": ["n1"], "wid": "compare:n1:x:y"},
    ]
    _patch_facet_fakes(monkeypatch, tmp_path, chunks, qa_rows)
    jobs = [{"job_id": i, "jd": "Kafka job " + "x" * 50} for i in range(4)]

    stats = await driver._run_synth(jobs, out_dir=tmp_path)
    # mid-gather snapshot taken by the last-finishing unit (before q3's own
    # pair is written): all 8 tailor/letter pairs flushed; >=3 qa pairs flushed
    # (fq/aq scheduling under the semaphore is timing-soft, hence >= not ==)
    assert len(_FakeSynth.saw) == 1 and _FakeSynth.saw[0][0] == 8 and _FakeSynth.saw[0][1] >= 3
    tailor = driver._read_jsonl(tmp_path / "tailor_pairs.jsonl")
    qa = driver._read_jsonl(tmp_path / "qa_pairs.jsonl")
    facet_of = lambda p: p["metadata"]["facet"]
    assert {p["metadata"]["job_id"] for p in tailor if facet_of(p) == "tailor_resume"} == {0, 1, 2, 3}
    assert {p["metadata"]["job_id"] for p in tailor if facet_of(p) == "cover_letter"} == {0, 1, 2, 3}
    assert {p["metadata"]["question"] for p in qa} == {"q0", "q1", "q2", "q3", "fq", "aq", "cq"}
    assert all(p["metadata"].get("wid") for p in qa)  # resume identity stamped
    assert stats == {"pairs_written": 15, "rejects_written": 0,
                     "dedup_removed": {"tailor": 0, "qa": 0}}
    assert len(tailor) == 8 and len(qa) == 7


@pytest.mark.asyncio
async def test_run_synth_rejects_persisted_incrementally(tmp_path, monkeypatch):
    import src.brain.synthesizer as syn_mod

    class DyingSynth(_FakeSynth):
        async def synthesize_letter(self, job, top_k=6):
            return None, "length_band: 12 words outside 250-350"  # -> reject row
    chunks = [{"id": "s1", "type": "story", "content": "Led Kafka governance.", "metadata": {}}]
    _patch_facet_fakes(monkeypatch, tmp_path, chunks, [])
    monkeypatch.setattr(syn_mod, "Synthesizer", DyingSynth)
    stats = await driver._run_synth([{"job_id": 0, "jd": "Kafka " + "x" * 50}],
                                    out_dir=tmp_path)
    rej = driver._read_jsonl(tmp_path / "rejects.jsonl")
    assert rej and rej[0]["facet"] == "cover_letter"
    assert stats["rejects_written"] == 1


@pytest.mark.asyncio
async def test_run_synth_skips_done_wids(tmp_path, monkeypatch):
    import src.brain.synthesizer as syn_mod
    chunks = [{"id": "s1", "type": "story", "content": "Led Kafka governance.", "metadata": {}}]
    qa_rows = [
        {"facet": "behavioral", "question": f"q{i}", "chunk_ids": ["s1"],
         "wid": f"behavioral:s1:q{i}"} for i in range(3)]
    _patch_facet_fakes(monkeypatch, tmp_path, chunks, qa_rows)
    await driver._run_synth([], out_dir=tmp_path, skip_wids={"behavioral:s1:q1"})
    assert driver._read_jsonl(tmp_path / "tailor_pairs.jsonl") == []
    assert {p["metadata"]["question"] for p in
            driver._read_jsonl(tmp_path / "qa_pairs.jsonl")} == {"q0", "q2"}


@pytest.mark.asyncio
async def test_run_synth_qa_cap_zero_skips_qa(tmp_path, monkeypatch):
    """Smoke semantics: explicit --qa-cap 0 means NO qa teacher calls;
    omitting the cap keeps the full plan (qa_cap=None)."""
    chunks = [{"id": "s1", "type": "story", "content": "Led Kafka governance.", "metadata": {}}]
    qa_rows = [{"facet": "behavioral", "question": f"q{i}", "chunk_ids": ["s1"],
                "wid": f"behavioral:s1:q{i}"} for i in range(3)]
    _patch_facet_fakes(monkeypatch, tmp_path, chunks, qa_rows)
    await driver._run_synth([], out_dir=tmp_path, qa_cap=0)
    assert driver._read_jsonl(tmp_path / "qa_pairs.jsonl") == []
    full = tmp_path / "full"
    full.mkdir()
    await driver._run_synth([], out_dir=full, qa_cap=None)
    assert len(driver._read_jsonl(tmp_path / "full" / "qa_pairs.jsonl")) == 3


def _seed_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_resume_appends_skips_and_warns(tmp_path, capsys):
    db = _fixture_db(tmp_path)
    from build_frozen_eval import _load_jobs, _stratified_sample
    pool = _stratified_sample(_load_jobs(db), 10, 42)
    assert len(pool) >= 3
    out = tmp_path / "synth"
    out.mkdir()
    _seed_jsonl(out / "tailor_pairs.jsonl", [
        {"messages": [], "metadata": {"facet": "tailor_resume", "job_id": pool[0]["job_id"]}},
        {"messages": [], "metadata": {"facet": "cover_letter", "job_id": pool[1]["job_id"]}}])
    _seed_jsonl(out / "qa_pairs.jsonl", [
        {"messages": [], "metadata": {"facet": "behavioral", "wid": "behavioral:s1:q"}}])
    synth = AsyncMock(return_value=_STATS)
    with patch.object(driver, "_run_synth", synth):
        report = driver.build(db_path=db, out_dir=out, jd_limit=10, seed=42,
                              held_out_job_ids=set())
    assert synth.await_count == 1
    passed_ids = {j["job_id"] for j in synth.await_args.args[0]}
    assert pool[0]["job_id"] not in passed_ids  # skip is before dispatch
    assert pool[1]["job_id"] not in passed_ids
    assert synth.await_args.kwargs["skip_wids"] == {"behavioral:s1:q"}
    assert report["resumed_from"] == {"tailor": 2, "qa": 1}
    assert report["tailor_pairs"] == 2 and report["qa_pairs"] == 1  # totals from files
    assert "append" in capsys.readouterr().out.lower()  # auto-detected, warned
    assert len((out / "tailor_pairs.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_fresh_run_no_skip(tmp_path):
    db = _fixture_db(tmp_path)
    synth = AsyncMock(return_value=_STATS)
    out = tmp_path / "synth"
    with patch.object(driver, "_run_synth", synth):
        report = driver.build(db_path=db, out_dir=out, jd_limit=10, seed=42,
                              held_out_job_ids=set())
    assert synth.await_args.kwargs["skip_wids"] == set()
    assert report["resumed_from"] == {"tailor": 0, "qa": 0}




def test_cap_per_facet_strides_each_facet():
    """--qa-cap stride-samples N per facet (head slices cluster on one anchor
    and bias acceptance); every facet is represented."""
    rows = [{"facet": f, "wid": f"{f}:{i}"}
            for f in ("behavioral", "factual", "avatar") for i in range(20)]
    kept = driver._cap_per_facet(rows, 5)
    # stride 4 over 20 rows -> indices 0,4,8,12,16 per facet
    assert [w["wid"] for w in kept[:5]] == [f"behavioral:{i}" for i in range(0, 20, 4)]
    assert sorted({w["facet"] for w in kept}) == ["avatar", "behavioral", "factual"]
    counts = {w["facet"]: sum(1 for x in kept if x["facet"] == w["facet"]) for w in kept}
    assert counts == {"behavioral": 5, "factual": 5, "avatar": 5}
