"""Build frozen eval sets (spec §4.1). Deterministic with --seed. Tailor gold stays null until P6."""
from __future__ import annotations

import argparse, hashlib, json, re, sqlite3
from pathlib import Path
from typing import Dict, List, Optional

NEGATIVE_PROBES = [
    "Tell me about a time you led a 20-person engineering org",
    "Describe your experience managing managers",
    "What was your role in the Kubernetes cluster migration?",
    "How did you use Rust in production?",
    "Walk me through the iOS app you shipped",
    "What about your PhD research?",
    "Describe your Salesforce administration experience",
    "Tell me about the time you got PMP certified",
    "How did you handle the Flink stream reprocessing incident?",
    "What was your on-call rotation like at Google?",
    "Describe your machine learning model deployment at a hedge fund",
    "Tell me about leading the SOC 2 audit as CISO",
]

_LEVEL_WORDS = re.compile(r"\b(senior|staff|principal|lead|jr|junior|ii|iii|iv|sr)\b", re.I)
_BUCKET_BY_MODE = {"qa": "factual", "auto": "factual", "avatar": "avatar"}
# B4: tailoring-mode seed questions are deliberately NOT bucketed -  they are
# tailoring requests, not interview questions.
_TARGETS = {"behavioral": 18, "factual": 18, "avatar": 7}

# B4 authored top-ups (spec §3.4 archetypes / §4.1 composition). Seed cannot
# reach 18 behavioral; factual tops up only when seed < 18.
AUTHORED_BEHAVIORAL = [
    "Tell me about a time you led a project without formal authority over the team",
    "Describe how you aligned two teams with conflicting priorities on a shared deliverable",
    "Tell me about a launch or release that failed. What happened and what did you change?",
    "Describe a time you built a solution from vague or incomplete requirements",
    "Give an example of mentoring a junior engineer through a difficult problem",
    "Tell me about a deadline where you had to cut scope. What did you trade and why?",
    "Describe a disagreement with your manager about a technical direction and how it ended",
    "Tell me about a time you influenced an architecture or governance decision across teams",
    "Describe a situation where you had to make a decision with incomplete data",
    "Tell me about a time you identified a risk nobody else had flagged",
    "Describe how you handled a production incident from detection to postmortem",
    "Tell me about a project where you onboarded new team members while still delivering",
    "Describe a time you pushed back on a requirement and proposed an alternative",
    "Tell me about balancing tech debt work against feature delivery",
    "Describe a cross-functional partnership that changed the outcome of your project",
    "Tell me about a time your first technical approach failed and you had to pivot",
    "Describe how you prioritized work when everything was marked urgent",
    "Tell me about a time you improved a process that outlived your involvement",
]

AUTHORED_FACTUAL = [
    "What is your experience with Apache Kafka and event streaming platforms?",
    "Describe your work with AWS services and which you used most in production",
    "What observability and monitoring tools have you worked with, and how?",
    "Explain your experience with GraphQL API design and implementation",
    "What is your experience with containerization and ECS or Kubernetes deployments?",
    "Describe your work with SQL Server or other relational databases at scale",
    "What experience do you have with OAuth2 and JWT authentication flows?",
    "Describe your experience building REST APIs and payment gateway integrations",
    "What is your experience with Python and FastAPI or similar frameworks?",
    "Describe your work with CI/CD pipelines and shift-left testing",
    "What experience do you have with schema registries and data contracts?",
    "Describe a system where you improved performance or throughput. What were the metrics?",
    "What is your experience with cloud cost optimization or serverless architectures?",
    "Describe your work with legacy modernization or migration projects",
    "What experience do you have mentoring or leading small teams?",
    "Describe your exposure to GenAI or LLM-based services in production",
    "What is your experience with caching layers and high-throughput data paths?",
    "Describe your work with infrastructure as code or developer experience tooling",
]

_AUTHORED = {"behavioral": AUTHORED_BEHAVIORAL, "factual": AUTHORED_FACTUAL}


def _slug_title(title: str) -> str:
    return _LEVEL_WORDS.sub("", title.lower()).strip()


def _load_jobs(db_path: Path) -> List[Dict]:
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT id, title, company, description FROM jobs "
        "WHERE description IS NOT NULL AND length(description) > 200").fetchall()
    con.close()
    seen, out = set(), []
    for jid, title, company, desc in rows:
        key = (title or "", company or "", hashlib.sha256(desc.encode()).hexdigest()[:16])
        if key in seen:
            continue
        seen.add(key)
        out.append({"job_id": jid, "title": title or "", "company": company or "", "jd": desc})
    return out


def _stratified_sample(jobs: List[Dict], n: int, seed: int) -> List[Dict]:
    import random
    rng = random.Random(seed)
    clusters: Dict[str, List[Dict]] = {}
    for j in jobs:
        clusters.setdefault(_slug_title(j["title"]), []).append(j)
    for v in clusters.values():
        rng.shuffle(v)
    picked: List[Dict] = []
    keys = sorted(clusters)
    while len(picked) < n and any(clusters[k] for k in keys):
        for k in keys:
            if clusters[k] and len(picked) < n:
                picked.append(clusters[k].pop())
    return picked


def _build_qa(suite_path: Path) -> List[Dict]:
    """Seed first, authored top-up to targets (B4) -  total always 55."""
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    buckets: Dict[str, List[Dict]] = {b: [] for b in _TARGETS}
    for i, q in enumerate(data.get("questions", [])):
        bucket = _BUCKET_BY_MODE.get(q.get("mode"))
        if bucket and len(buckets[bucket]) < _TARGETS[bucket]:
            buckets[bucket].append({"id": q.get("id", f"mig_{i}"), "query": q["query"],
                                    "mode": q.get("mode", "qa"), "bucket": bucket,
                                    "expected": "answer"})
    for bucket, authored in _AUTHORED.items():
        for j, text in enumerate(authored):
            if len(buckets[bucket]) >= _TARGETS[bucket]:
                break
            buckets[bucket].append({"id": f"auth_{bucket}_{j}", "query": text,
                                    "mode": "qa", "bucket": bucket,
                                    "expected": "answer"})
    out: List[Dict] = []
    for b in ("behavioral", "factual", "avatar"):
        out.extend(buckets[b])
    for i, probe in enumerate(NEGATIVE_PROBES):
        out.append({"id": f"probe_{i}", "query": probe, "mode": "qa",
                    "bucket": "negative_probe", "expected": "admit"})
    return out


def build(db_path: Path, suite_path: Path, out_dir: Path, n_tailor: int = 160,
          seed: int = 42) -> Dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = _load_jobs(db_path)
    tailor = _stratified_sample(jobs, min(n_tailor, len(jobs)), seed)
    for row in tailor:
        row["gold"] = None
    with open(out_dir / "tailor_frozen.jsonl", "w", encoding="utf-8") as f:
        for row in tailor:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    qa = _build_qa(suite_path)
    with open(out_dir / "qa_frozen.jsonl", "w", encoding="utf-8") as f:
        for row in qa:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {"seed": seed, "counts": {"tailor": len(tailor), "qa": len(qa)}, "files": {}}
    for name in ("tailor_frozen.jsonl", "qa_frozen.jsonl"):
        blob = (out_dir / name).read_bytes()
        manifest["files"][name] = hashlib.sha256(blob).hexdigest()
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/careergraph.db")
    ap.add_argument("--suite", default="data/brain/eval_suite.json")
    ap.add_argument("--out-dir", default="data/brain/eval")
    ap.add_argument("--n-tailor", type=int, default=160)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    m = build(Path(a.db), Path(a.suite), Path(a.out_dir), a.n_tailor, a.seed)
    print(json.dumps(m, indent=2))
