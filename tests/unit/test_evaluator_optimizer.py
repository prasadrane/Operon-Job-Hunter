"""Unit tests for FactGuard dynamic graph validation, EvaluatorPanel 3-persona scoring, and SurgicalOptimizer delta patching."""

import importlib
import pytest
import networkx as nx

fact_guard_mod = importlib.import_module("src.pipeline.3_tailoring.fact_guard")
FactGuard = fact_guard_mod.FactGuard

evaluator_panel_mod = importlib.import_module("src.pipeline.3_tailoring.evaluator_panel")
EvaluatorPanel = evaluator_panel_mod.EvaluatorPanel

surgical_mod = importlib.import_module("src.pipeline.3_tailoring.surgical_optimizer")
SurgicalOptimizer = surgical_mod.SurgicalOptimizer

builder_mod = importlib.import_module("src.pipeline.3_tailoring.career_graph_builder")
CareerGraphBuilder = builder_mod.CareerGraphBuilder


SAMPLE_RESUME = """
# Senior Software Engineer — Rocket Mortgage
## Projects
### Distributed Stream Pipeline
- Architected high-throughput Kafka streaming pipeline processing 10M+ daily events with 99.99% uptime.
- Implemented C# microservices, Redis caching, and Docker containers reducing latency by 45%.
"""


def test_factguard_blocks_unverified_technologies():
    guard = FactGuard(custom_unverified=["Solidity", "Rust", "Ethereum"])
    valid, reason = guard.validate_bullet("Built scalable C# microservices and Kafka streaming pipeline.")
    assert valid is True

    invalid, reason = guard.validate_bullet("Architected Solidity smart contracts on Ethereum blockchain.")
    assert invalid is False
    assert "Solidity" in reason or "Ethereum" in reason


def test_factguard_dynamic_graph_validation():
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME)

    guard = FactGuard(graph=graph)

    # Grounded bullet should pass
    valid, reason = guard.validate_bullet("Architected Kafka streaming pipeline with Docker and Redis.")
    assert valid is True

    # Bullet with unverified tech not in graph
    invalid_tech, reason_tech = guard.validate_bullet("Engineered Rust blockchain consensus with Solana smart contracts.")
    assert invalid_tech is False
    assert "Rust" in reason_tech or "Solana" in reason_tech or "unverified" in reason_tech.lower()

    # Bullet with exorbitant/unverified metric claim
    invalid_metric, reason_metric = guard.validate_bullet("Managed $50B infrastructure portfolio.")
    assert invalid_metric is False
    assert "exorbitant" in reason_metric.lower() or "scope" in reason_metric.lower() or "50" in reason_metric


def test_evaluator_panel_persona_weighted_scoring():
    panel = EvaluatorPanel()
    assert panel.weights["hiring_manager"] == 0.40
    assert panel.weights["ats_scanner"] == 0.35
    assert panel.weights["recruiter"] == 0.25

    bullets = [
        "Architected high-throughput Kafka streaming pipeline processing 10M+ daily events with 99.99% uptime.",
        "Implemented C# microservices and Redis caching reducing latency by 45%."
    ]
    target_keywords = ["Kafka", "C#", "Redis"]

    result = panel.evaluate_draft(bullets, target_keywords)

    assert "composite_score" in result
    assert "hm_score" in result
    assert "ats_score" in result
    assert "recruiter_score" in result
    assert "critiques" in result

    expected_composite = (
        0.40 * result["hm_score"] +
        0.35 * result["ats_score"] +
        0.25 * result["recruiter_score"]
    )
    assert pytest.approx(result["composite_score"], 0.01) == expected_composite
    assert result["passed"] is True


def test_evaluator_panel_emits_critiques_on_weak_draft():
    panel = EvaluatorPanel()
    weak_bullets = [
        "Worked on backend tasks and wrote code.",
        "Helped team with meetings and bug fixes."
    ]
    target_keywords = ["Kubernetes", "Kafka", "GraphQL"]

    result = panel.evaluate_draft(weak_bullets, target_keywords)

    assert result["passed"] is False
    assert len(result["critiques"]) > 0
    assert any("bullet_index" in c for c in result["critiques"])


def test_surgical_delta_patch_and_regex_linter():
    optimizer = SurgicalOptimizer()
    original_bullets = [
        "Architected Kafka event pipeline processing 10M+ events/day.",
        "Built C# backend services for mortgage loan calculation.",
        "Designed Redis caching layer reducing database reads by 40%."
    ]
    critiques = [{
        "bullet_index": 1,
        "suggested_patch": "Engineered C# backend services for mortgage loan calculation."
    }]

    patched = optimizer.apply_patches(original_bullets, critiques)
    assert "Engineered" in patched[1]
    assert len({b.split()[0] for b in patched}) == 3


def test_surgical_optimizer_deduplicates_duplicate_action_verbs():
    optimizer = SurgicalOptimizer()
    bullets_with_duplicates = [
        "Architected distributed streaming platform with Kafka.",
        "Architected scalable microservices with C# and .NET 8.",
        "Built data pipeline with Redis.",
        "Built REST API with FastAPI."
    ]

    deduped = optimizer.apply_patches(bullets_with_duplicates, critiques=[])
    leading_verbs = [b.split()[0] for b in deduped]

    # Leading verbs must all be unique
    assert len(leading_verbs) == len(set(leading_verbs))
    assert leading_verbs[0] == "Architected"
    assert leading_verbs[1] != "Architected"
    assert leading_verbs[2] == "Built"
    assert leading_verbs[3] != "Built"
