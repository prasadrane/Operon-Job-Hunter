import sys
from pathlib import Path

# Add project root to sys.path
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

job = JobPosting(
    id="job_fintech_1",
    company="Stripe",
    title="Staff Backend Platform Engineer",
    url="https://stripe.com/jobs/1",
    description="Seeking Staff Engineer with 10+ years in distributed systems, C#/.NET Core, AWS, Kafka, high concurrency, and event-driven architecture.",
)

eval_questions = [
    {"id": "Q1_Interview_Kafka", "category": "Interview Prep", "q": "Tell me about your experience architecting and governing Kafka or event-driven systems.", "mode": "avatar"},
    {"id": "Q2_Interview_Observability", "category": "Interview Prep", "q": "Describe a time you diagnosed and resolved a high-severity production observability or performance bottleneck.", "mode": "avatar"},
    {"id": "Q3_Interview_CloudMig", "category": "Interview Prep", "q": "How did you lead the legacy monolith migration to cloud-native microservices on AWS?", "mode": "avatar"},
    {"id": "Q4_Interview_Security", "category": "Interview Prep", "q": "Walk me through how you handled OAuth2 / JWT authentication migration across multiple teams without downtime.", "mode": "avatar"},
    {"id": "Q5_Interview_GenAI", "category": "Interview Prep", "q": "What is your hands-on experience with Amazon Bedrock, LLM orchestration, and Intent routing?", "mode": "avatar"},
    {"id": "Q6_Screening_WhyUs", "category": "Application Form", "q": "Why are you interested in this Staff Backend Platform Engineer role and how does your background fit our stack?", "mode": "avatar"},
    {"id": "Q7_Screening_Leadership", "category": "Application Form", "q": "Give an example of driving technical standards adoption across multiple engineering teams without direct managerial mandate.", "mode": "avatar"},
    {"id": "Q8_Screening_WorkAuth", "category": "Application Form", "q": "What is your current work authorization status and sponsorship requirements?", "mode": "qa"},
    {"id": "Q9_Tailoring_Concurrency", "category": "Resume Tailoring", "q": "Tailor 3 resume bullet points highlighting high-concurrency performance tuning and thread profiling.", "mode": "tailoring"},
    {"id": "Q10_Boundary_UnfamiliarTech", "category": "Boundary/Negative Control", "q": "Describe your production experience with Rust, Haskell, and COBOL mainframes.", "mode": "avatar"},
]

print("=== RUNNING 10-QUESTION BENCHMARK: BASELINE vs CAREER BRAIN ===")

report = []
for item in eval_questions:
    q = item["q"]
    qid = item["id"]
    cat = item["category"]
    print(f"\nEvaluating {qid} [{cat}]...")
    
    # 1. Baseline
    t0 = time.time()
    ans_base = baseline._answer_custom_question(q, job.company, job.title, job.description)
    lat_base = (time.time() - t0) * 1000
    
    # 2. Career Brain
    t1 = time.time()
    res_brain = brain_q4.query(q, mode=item["mode"], job_desc=job.description)
    lat_brain = (time.time() - t1) * 1000
    
    entry = {
        "id": qid,
        "category": cat,
        "question": q,
        "mode": res_brain.mode,
        "baseline": {
            "answer": ans_base,
            "latency_ms": lat_base,
        },
        "career_brain": {
            "answer": res_brain.answer,
            "confidence": res_brain.confidence,
            "citations": [c.chunk_id for c in res_brain.citations],
            "warnings": res_brain.warnings,
            "latency_ms": lat_brain,
        },
    }
    report.append(entry)
    print(f"  [OK] Baseline: {lat_base:.0f}ms")
    print(f"  [OK] Brain: {lat_brain:.0f}ms (Conf: {res_brain.confidence:.2f})")

out_path = Path("data/brain/comparative_benchmark_results.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("\nBENCHMARK COMPLETE. Saved to data/brain/comparative_benchmark_results.json")
