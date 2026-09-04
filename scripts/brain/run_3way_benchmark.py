import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib
import json
import time

QAGenerator = importlib.import_module("src.pipeline.3_tailoring.qa_generator").QAGenerator
from src.brain.inference import BrainInference
from src.brain.ollama_client import OllamaClient
from src.core.models import JobPosting

baseline = QAGenerator()
brain_q4 = BrainInference(ollama_client=OllamaClient(model="career-brain-q4"))
brain_q8 = BrainInference(ollama_client=OllamaClient(model="career-brain"))

job = JobPosting(
    id="job_fintech_1",
    company="Stripe",
    title="Staff Backend Platform Engineer",
    url="https://stripe.com/jobs/1",
    description="Seeking Staff Engineer with 10+ years in distributed systems, C#/.NET Core, AWS, Kafka, high concurrency, and event-driven architecture.",
)

questions = [
    {
        "id": "T1_Kafka_Governance",
        "category": "Technical Architecture",
        "q": "Tell me about your experience architecting and governing Kafka or event-driven systems.",
        "mode": "avatar"
    },
    {
        "id": "T2_Observability_Diagnostics",
        "category": "Debugging & Performance",
        "q": "Describe a time you diagnosed and resolved a high-severity production observability or performance bottleneck.",
        "mode": "avatar"
    },
    {
        "id": "T3_Bedrock_GenAI",
        "category": "AI / Modern Stack",
        "q": "What is your hands-on experience with Amazon Bedrock, LLM orchestration, and Intent routing?",
        "mode": "avatar"
    },
    {
        "id": "T4_Tailoring_FinTech",
        "category": "Resume Tailoring",
        "q": "Tailor 3 resume bullet points highlighting high-concurrency performance tuning and thread profiling for Stripe.",
        "mode": "tailoring"
    },
    {
        "id": "T5_Negative_Boundary",
        "category": "Hallucination Boundary",
        "q": "Describe your production experience with Rust, Haskell, and COBOL mainframes.",
        "mode": "avatar"
    }
]

print("=== 3-WAY COMPARISON: BASELINE vs Q4 BRAIN vs Q8 BRAIN ===")

results = []
for item in questions:
    q = item["q"]
    qid = item["id"]
    cat = item["category"]
    print(f"\n[Evaluating {qid}: {cat}]")
    print(f"Q: {q}")
    
    # 1. Baseline
    t0 = time.time()
    ans_base = baseline._answer_custom_question(q, job.company, job.title, job.description)
    lat_base = (time.time() - t0) * 1000
    print(f"  - Baseline done: {lat_base:.0f}ms")
    
    # 2. Q4 Brain
    t1 = time.time()
    res_q4 = brain_q4.query(q, mode=item["mode"], job_desc=job.description)
    lat_q4 = (time.time() - t1) * 1000
    print(f"  - Q4 Brain done: {lat_q4:.0f}ms (Conf: {res_q4.confidence:.2f})")
    
    # 3. Q8 Brain
    t2 = time.time()
    res_q8 = brain_q8.query(q, mode=item["mode"], job_desc=job.description)
    lat_q8 = (time.time() - t2) * 1000
    print(f"  - Q8 Brain done: {lat_q8:.0f}ms (Conf: {res_q8.confidence:.2f})")
    
    results.append({
        "id": qid,
        "category": cat,
        "question": q,
        "baseline": {
            "answer": ans_base,
            "latency_ms": lat_base
        },
        "q4_brain": {
            "answer": res_q4.answer,
            "confidence": res_q4.confidence,
            "warnings": res_q4.warnings,
            "latency_ms": lat_q4
        },
        "q8_brain": {
            "answer": res_q8.answer,
            "confidence": res_q8.confidence,
            "warnings": res_q8.warnings,
            "latency_ms": lat_q8
        }
    })

out_path = Path("data/brain/3way_benchmark_results.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("\n3-WAY BENCHMARK COMPLETE. Saved to data/brain/3way_benchmark_results.json")
