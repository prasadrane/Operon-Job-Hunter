"""Unit tests for Phase 3 Interview Intelligence & Tailored Study Guide Copilot:
- StudyGuideGenerator (3-track study guide: System Design, Behavioral STAR, Reverse Questions)
- STARSimulator (graph-grounded STAR narrative generation from NetworkX DiGraph)
- Markdown packet formatting for Telegram attachments
- Graceful handling of empty or sparse career graphs
"""

from __future__ import annotations

import importlib
import pytest
import networkx as nx

from src.agents.interview.study_guide_generator import StudyGuideGenerator, StudyGuide
from src.agents.interview.star_simulator import STARSimulator, STARNarrative

# Dynamic imports for numbered package directory
graph_builder_mod = importlib.import_module("src.pipeline.3_tailoring.career_graph_builder")
CareerGraphBuilder = graph_builder_mod.CareerGraphBuilder


@pytest.fixture
def sample_career_graph() -> nx.DiGraph:
    """Fixture providing a populated NetworkX DiGraph with projects, technologies, and metrics."""
    builder = CareerGraphBuilder()
    resume_text = """
# Senior Distributed Systems Engineer — Stripe
### Real-Time Payment Settlement Engine
- Architected distributed payment settlement pipeline using Kafka, Go, and PostgreSQL processing 50M+ transactions daily.
- Reduced transaction settlement latency by 45% and achieved 99.999% system availability.
- Led cross-functional migration from legacy monolith to Kubernetes microservices reducing AWS cloud costs by $1.2M annually.

### Fraud Detection Stream Processor
- Implemented real-time anomaly detection service with Python, Redis, and FastAPI handling 15,000 requests/sec.
- Decreased fraudulent transaction false-positive rate by 30%.
"""
    return builder.build_from_text(resume_text)


# ============================================================================
# 1. 3-Track Study Guide Generation Tests
# ============================================================================

def test_study_guide_generation_basic():
    """Verify basic study guide generation with minimal inputs."""
    generator = StudyGuideGenerator()
    guide = generator.generate_interview_prep(
        job_title="Staff Backend Engineer",
        company="Uber",
        graph_nodes=[{"name": "Kafka", "bullet": "10M+ daily events, 99.99% uptime"}],
    )
    assert guide["company"] == "Uber"
    assert guide["job_title"] == "Staff Backend Engineer"
    assert len(guide["system_design_topics"]) > 0
    assert len(guide["behavioral_star_talking_points"]) > 0
    assert len(guide["reverse_interview_questions"]) > 0


def test_three_track_study_guide_structure(sample_career_graph):
    """Verify 3-Track preparation guide creates structured sections: System Design, STAR Stories, Reverse Questions."""
    generator = StudyGuideGenerator()
    guide = generator.generate_interview_prep(
        job_title="Principal Infrastructure Architect",
        company="Netflix",
        graph=sample_career_graph,
        job_description="Architecting ultra-low-latency global stream processing on AWS and Kubernetes.",
    )

    # Track 1: System Design
    assert len(guide["system_design_topics"]) >= 2
    assert any("System Design" in topic or "Architecture" in topic for topic in guide["system_design_topics"])

    # Track 2: Behavioral STAR Stories
    assert len(guide["behavioral_star_talking_points"]) >= 2
    assert any("50M+" in str(pt) or "45%" in str(pt) or "Stripe" in str(pt) for pt in guide["behavioral_star_talking_points"])

    # Track 3: Reverse-Interview Technical Questions
    assert len(guide["reverse_interview_questions"]) >= 3
    assert any("Netflix" in q or "architecture" in q.lower() or "latency" in q.lower() for q in guide["reverse_interview_questions"])


# ============================================================================
# 2. Graph-Grounded STAR Narrative Generation (STARSimulator)
# ============================================================================

def test_star_simulator_generates_grounded_narratives(sample_career_graph):
    """Verify STARSimulator extracts grounded Situation, Task, Action, and Result from graph edges."""
    simulator = STARSimulator()
    narratives = simulator.generate_narratives(sample_career_graph)

    assert len(narratives) >= 2
    first = narratives[0]
    assert isinstance(first, STARNarrative)
    assert first.situation != ""
    assert first.task != ""
    assert first.action != ""
    assert first.result != ""
    assert len(first.technologies) > 0
    assert len(first.metrics) > 0

    # Ensure full markdown representation works
    md = first.to_markdown()
    assert "**Situation:**" in md
    assert "**Task:**" in md
    assert "**Action:**" in md
    assert "**Result:**" in md


def test_star_simulator_simulate_behavioral_response(sample_career_graph):
    """Verify STARSimulator selects the most relevant narrative for a target behavioral prompt."""
    simulator = STARSimulator()
    response = simulator.simulate_response(
        question="Tell me about a high-scale stream processing project where you improved system performance or reliability.",
        graph=sample_career_graph,
    )
    assert isinstance(response, STARNarrative)
    assert any(tech in response.action or tech in response.technologies for tech in ["Kafka", "Redis", "Python", "Go"])
    assert any(m in response.result or m in response.metrics for m in ["45%", "99.999%", "30%", "15,000", "50M+"])


# ============================================================================
# 3. Markdown Formatting for Telegram Attachments
# ============================================================================

def test_study_guide_markdown_packet_formatting(sample_career_graph):
    """Verify generated Markdown study guide is properly structured for export or Telegram dispatch."""
    generator = StudyGuideGenerator()
    guide = generator.generate_interview_prep(
        job_title="Staff Distributed Systems Engineer",
        company="Databricks",
        graph=sample_career_graph,
    )

    markdown_packet = generator.format_markdown_packet(guide)

    assert "# Interview Intelligence & Study Guide" in markdown_packet
    assert "Databricks" in markdown_packet
    assert "Staff Distributed Systems Engineer" in markdown_packet
    assert "## Track 1: System Design Architectures & Deep Dives" in markdown_packet
    assert "## Track 2: Graph-Grounded Behavioral STAR Narratives" in markdown_packet
    assert "## Track 3: Reverse-Interview Technical Questions" in markdown_packet
    assert "Generated by CareerGraph-AI Interview Copilot" in markdown_packet


# ============================================================================
# 4. Empty & Sparse Graph Handling (Graceful Fallbacks)
# ============================================================================

def test_empty_graph_handling():
    """Verify generator and simulator handle empty graph gracefully without crashes."""
    empty_graph = nx.DiGraph()
    generator = StudyGuideGenerator()
    simulator = STARSimulator()

    # Simulator with empty graph
    narratives = simulator.generate_narratives(empty_graph)
    assert len(narratives) >= 1
    assert "Core engineering leadership" in narratives[0].situation or "Key Project" in narratives[0].project_name

    # Generator with empty graph
    guide = generator.generate_interview_prep(
        job_title="Senior Software Engineer",
        company="Acme Corp",
        graph=empty_graph,
    )
    assert guide["company"] == "Acme Corp"
    assert len(guide["system_design_topics"]) > 0
    assert len(guide["behavioral_star_talking_points"]) > 0
    assert len(guide["reverse_interview_questions"]) > 0

    packet = generator.format_markdown_packet(guide)
    assert "Acme Corp" in packet
    assert "Track 1" in packet


def test_generator_dict_nodes_input_support():
    """Verify generator supports graph_nodes as a list of dicts for backward compatibility."""
    generator = StudyGuideGenerator()
    raw_nodes = [
        {"name": "GraphQL Gateway", "bullet": "Handled 20M req/day with 99.9% uptime using Node.js and Redis"},
        {"name": "Database Sharding", "bullet": "Migrated 5TB MySQL cluster with zero downtime"},
    ]
    guide = generator.generate_interview_prep(
        job_title="Lead Backend Engineer",
        company="Shopify",
        graph_nodes=raw_nodes,
    )
    assert guide["company"] == "Shopify"
    assert len(guide["behavioral_star_talking_points"]) == 2
    assert "GraphQL Gateway" in guide["behavioral_star_talking_points"][0]
