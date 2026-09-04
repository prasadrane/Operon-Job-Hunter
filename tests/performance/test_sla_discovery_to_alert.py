"""Performance & SLA Benchmark Test Suite for Phase 1 Agentic Architecture.

Validates that the end-to-end pipeline from job discovery through 7-Block evaluation,
GraphRAG candidate knowledge retrieval, and resume tailoring completes within the
strict <45s SLA threshold before triggering the Human-In-The-Loop (HITL) alert.
"""

import concurrent.futures
import importlib
import time
import pytest
from src.core.db.dual_engine import init_dual_database_pool
from src.pipeline.state_machine import build_careergraph_pipeline

_builder_mod = importlib.import_module("src.pipeline.3_tailoring.career_graph_builder")
CareerGraphBuilder = _builder_mod.CareerGraphBuilder


SAMPLE_RESUME = """
# Senior Distributed Systems Engineer — Datadog
### Real-Time Streaming Telemetry
- Architected high-throughput Kafka streaming pipeline ingesting 10M+ events/day with Python and C#.
- Implemented Redis distributed caching layer reducing API query latency by 45%.
- Deployed microservices on AWS ECS Fargate with 99.99% uptime.
"""


def test_end_to_end_discovery_to_alert_sla_under_45s(tmp_path):
    """Verify single job posting discovery-to-HITL-alert executes in under 45.0 seconds."""
    checkpoints_db = str(tmp_path / "checkpoints_bench.db")
    telemetry_db = str(tmp_path / "telemetry_bench.db")
    init_dual_database_pool(checkpoints_path=checkpoints_db, telemetry_path=telemetry_db)

    # Initialize candidate graph
    builder = CareerGraphBuilder()
    builder.build_from_text(SAMPLE_RESUME)

    app = build_careergraph_pipeline(checkpoints_db_path=checkpoints_db)

    config = {"configurable": {"thread_id": "job_bench_001"}}
    state = {
        "job_id": "job_bench_001",
        "company": "Datadog",
        "title": "Principal Distributed Systems Engineer",
        "url": "https://boards.greenhouse.io/datadog/jobs/001",
        "portal_type": "greenhouse",
        "fit_score": 96.0,
        "current_stage": "DISCOVERED",
        "is_ghost_job": False,
        "work_auth_blocker": False,
        "resume_pdf_path": None,
        "cover_letter_path": None,
        "submission_receipt_id": None,
        "qa_answers": {},
        "audit_logs": [],
        "errors": [],
        "evaluator_critiques": [],
    }

    t0 = time.perf_counter()
    result = app.invoke(state, config=config)
    duration_s = time.perf_counter() - t0

    assert duration_s < 45.0, f"Discovery-to-alert SLA exceeded: {duration_s:.2f}s >= 45.0s"
    assert result["current_stage"] == "READY_FOR_HITL"
    assert result["resume_pdf_path"] is not None
    assert result["fit_score"] >= 85.0


def test_batch_discovery_to_alert_sla_under_45s(tmp_path):
    """Verify concurrent multi-job pipeline execution respects the SLA benchmark."""
    checkpoints_db = str(tmp_path / "checkpoints_batch_bench.db")
    telemetry_db = str(tmp_path / "telemetry_batch_bench.db")
    init_dual_database_pool(checkpoints_path=checkpoints_db, telemetry_path=telemetry_db)

    app = build_careergraph_pipeline(checkpoints_db_path=checkpoints_db)

    job_ids = [f"job_batch_bench_{i:03d}" for i in range(1, 4)]

    def run_single_job(jid: str):
        config = {"configurable": {"thread_id": jid}}
        state = {
            "job_id": jid,
            "company": f"TechCorp-{jid}",
            "title": "Staff Backend Engineer",
            "url": f"https://boards.greenhouse.io/techcorp/jobs/{jid}",
            "portal_type": "greenhouse",
            "fit_score": 92.0,
            "current_stage": "DISCOVERED",
            "is_ghost_job": False,
            "work_auth_blocker": False,
            "resume_pdf_path": None,
            "cover_letter_path": None,
            "submission_receipt_id": None,
            "qa_answers": {},
            "audit_logs": [],
            "errors": [],
            "evaluator_critiques": [],
        }
        return app.invoke(state, config=config)

    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(run_single_job, job_ids))
    total_duration_s = time.perf_counter() - t0

    assert total_duration_s < 45.0, f"Batch SLA exceeded: {total_duration_s:.2f}s >= 45.0s"
    for res in results:
        assert res["current_stage"] == "READY_FOR_HITL"
        assert res["resume_pdf_path"] is not None
