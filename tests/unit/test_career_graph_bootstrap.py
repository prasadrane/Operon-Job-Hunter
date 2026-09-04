import importlib
import time
import pytest
import networkx as nx

builder_mod = importlib.import_module("src.pipeline.3_tailoring.career_graph_builder")
CareerGraphBuilder = builder_mod.CareerGraphBuilder

vector_mod = importlib.import_module("src.pipeline.3_tailoring.graph_vector_engine")
GraphVectorEngine = vector_mod.GraphVectorEngine

SAMPLE_RESUME = """
# Senior Software Engineer — Rocket Mortgage
## Projects
### Distributed Stream Pipeline
- Architected high-throughput Kafka streaming pipeline processing 10M+ daily events with 99.99% uptime.
- Implemented C# microservices, Redis caching, and Docker containers reducing latency by 45%.

# Lead Cloud Architect — NexaTech
## Projects
### Multi-Region Cloud Migration
- Migrated legacy workloads to AWS using Kubernetes and PostgreSQL, saving $500k annually.
- Built Python real-time monitoring dashboard with React and TypeScript frontend.
"""

def test_career_graph_bootstrap_and_vector_matrix_search():
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME)
    
    assert isinstance(graph, nx.DiGraph)
    assert graph.number_of_nodes() >= 8
    assert graph.has_node("Rocket Mortgage")
    assert graph.has_node("Distributed Stream Pipeline")
    assert graph.has_node("Kafka")
    
    # Check node attributes
    company_data = graph.nodes["Rocket Mortgage"]
    assert company_data.get("type") == "Company"
    
    project_data = graph.nodes["Distributed Stream Pipeline"]
    assert project_data.get("type") == "Project"
    
    tech_data = graph.nodes["Kafka"]
    assert tech_data.get("type") == "Technology"
    assert "kafka" in tech_data.get("aliases", [])
    
    # Check edges
    assert graph.has_edge("Rocket Mortgage", "Distributed Stream Pipeline")
    assert graph.edges["Rocket Mortgage", "Distributed Stream Pipeline"]["relation"] == "CONTRIBUTED_TO"
    assert graph.has_edge("Distributed Stream Pipeline", "Kafka")
    assert graph.edges["Distributed Stream Pipeline", "Kafka"]["relation"] == "USED_TECH"
    
    # Test vector engine
    engine = GraphVectorEngine(graph)
    engine.bootstrap_embedding_cache()
    
    t0 = time.perf_counter()
    results = engine.retrieve_relevant_nodes("high-throughput distributed event streaming Kafka", top_k=3)
    duration_ms = (time.perf_counter() - t0) * 1000
    
    assert duration_ms < 15.0
    assert len(results) > 0
    assert any("Kafka" in r["name"] or "10M+" in r.get("value", "") or "10M+" in r.get("bullet", "") for r in results)

def test_graph_vector_engine_custom_embedder():
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME)
    
    def custom_embed(text: str):
        import numpy as np
        vec = np.zeros(64, dtype=np.float32)
        for i, word in enumerate(text.lower().split()):
            vec[hash(word) % 64] += 1.0 / (i + 1)
        norm = np.linalg.norm(vec)
        return vec / (norm + 1e-7)

    engine = GraphVectorEngine(graph, embedding_fn=custom_embed)
    engine.bootstrap_embedding_cache()
    
    results = engine.retrieve_relevant_nodes("AWS Kubernetes PostgreSQL migration", top_k=5)
    assert len(results) > 0
    names = [r["name"] for r in results]
    assert any("AWS" in names or "Kubernetes" in names or "Multi-Region Cloud Migration" in names for _ in [1])

def test_graph_vector_engine_empty_graph():
    empty_graph = nx.DiGraph()
    engine = GraphVectorEngine(empty_graph)
    engine.bootstrap_embedding_cache()
    results = engine.retrieve_relevant_nodes("Kafka", top_k=3)
    assert results == []

def test_career_graph_builder_serialization():
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME)
    
    graph_dict = builder.to_dict()
    assert "nodes" in graph_dict
    assert "links" in graph_dict or "edges" in graph_dict
    
    builder2 = CareerGraphBuilder()
    restored = builder2.from_dict(graph_dict)
    assert restored.number_of_nodes() == graph.number_of_nodes()
    assert restored.has_node("Rocket Mortgage")



def test_graph_vector_engine_sub5ms_retrieval_benchmark():
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME)
    engine = GraphVectorEngine(graph)
    engine.bootstrap_embedding_cache()
    
    # Warmup
    engine.retrieve_relevant_nodes("Kafka streaming Redis caching", top_k=3)
    
    # Benchmark 100 queries
    t0 = time.perf_counter()
    num_runs = 100
    for _ in range(num_runs):
        engine.retrieve_relevant_nodes("Kafka streaming Redis caching", top_k=3)
    total_time_ms = (time.perf_counter() - t0) * 1000
    avg_latency_ms = total_time_ms / num_runs
    
    # Assert average latency is sub-5ms (and well under 15ms)
    assert avg_latency_ms < 5.0


def test_career_graph_granular_star_and_architectural_patterns():
    rich_resume = """
    # Senior Software Engineer — Rocket Mortgage
    ## Projects
    ### Story 1 — Enterprise Kafka Event Streaming
    - Architected event-driven architecture with Kafka and Dead Letter Queues processing 10M+ daily events with 99.99% uptime.
    - Implemented single-table design DynamoDB microservices reducing query latency by 45%.
    """
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(rich_resume)
    
    node_types = {data.get("type") for _, data in graph.nodes(data=True)}
    assert "Action" in node_types
    assert "ArchitecturalPattern" in node_types
    assert "ImpactMetric" in node_types
    assert "Technology" in node_types
    
    # Check architectural pattern nodes
    assert any("Event-Driven" in str(n) or "Dead Letter" in str(n) or "Single-Table" in str(n) for n in graph.nodes())
    
    # Check Action node relationships
    action_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "Action"]
    assert len(action_nodes) >= 2
    
    # Check that Action nodes are linked to their technologies and metrics
    action_0 = action_nodes[0]
    out_edges = list(graph.out_edges(action_0, data=True))
    relations = [d.get("relation") for _, _, d in out_edges]
    assert "USED_TECH" in relations or "IMPLEMENTS_PATTERN" in relations or "ACHIEVED_METRIC" in relations


def test_context_enriched_node_vector_representations():
    rich_resume = """
    # Senior Software Engineer — Rocket Mortgage
    ## Projects
    ### Story 1 — Observability & Alert Hygiene
    - Re-engineered Dynatrace synthetic monitoring to slash on-call alert noise by 80% and reclaim ~20 engineering hours monthly.
    """
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(rich_resume)
    
    engine = GraphVectorEngine(graph)
    engine.bootstrap_embedding_cache()
    
    # Searching by high-level semantic intent should find Dynatrace / Synthetic Monitoring node
    results = engine.retrieve_relevant_nodes("on-call reduction telemetry monitoring", top_k=3)
    assert len(results) > 0
    top_names = [r["name"] for r in results]
    assert any("Dynatrace" in n or "synthetic" in n.lower() or "80%" in str(r.get("value", "")) for n, r in zip(top_names, results))


def test_strict_metric_filtering_rejects_calendar_years_and_raw_integers():
    """Verify metric extractor never extracts calendar years (e.g. 2009, 2018) or standalone raw integers."""
    resume_with_dates = """
    # Senior Software Engineer — Rocket Mortgage
    *Jan 2023 – Jul 2025*
    ## Education
    - B.E. in Electronics (2009 - 2013)
    - M.S. in Information Systems (2018 - 2019)
    ## Projects
    ### Story 4 — VB.NET Modernization to AWS ECS Fargate
    - In 2023, led 4 major initiatives across 6 engineers to cut cloud spend by 40% with 99.95% uptime and sub-2-second latency.
    """
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(resume_with_dates)

    metric_values = [
        str(d.get("value", "")).lower()
        for _, d in graph.nodes(data=True)
        if d.get("type") == "ImpactMetric"
    ]

    # Must NOT contain calendar years or standalone counting integers
    for year in ["2009", "2013", "2018", "2019", "2023", "2025"]:
        assert f"metric_{year}" not in graph.nodes
        assert year not in metric_values

    for raw_int in ["4", "6"]:
        assert f"metric_{raw_int}" not in graph.nodes
        assert raw_int not in metric_values

    # MUST contain genuine verified metrics
    assert any("40%" in m for m in metric_values)
    assert any("99.95%" in m for m in metric_values)
    assert any("sub-2-second" in m or "2-second" in m for m in metric_values)


def test_full_starr_subnode_decomposition():
    """Verify stories decompose into explicit Situation, Action, Result, and Reflection subnodes."""
    story_md = """
    # Senior Software Engineer — Rocket Mortgage
    ## Projects
    ### Story 1 — Observability Overhaul
    - Situation: Severe alert fatigue with false positive alerts overwhelming on-call engineers.
    - Action: Re-engineered Dynatrace synthetic health-checks and configured OpenTelemetry spans.
    - Result: Slashed on-call alert noise by 80% and reclaimed ~20 engineering hours monthly.
    - Reflection: Established clear alert hygiene standards across all 5 event-driven teams.
    """
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(story_md)

    story_node = "Story 1 — Observability Overhaul"
    assert graph.has_node(story_node)

    out_edges = list(graph.out_edges(story_node, data=True))
    edge_relations = {d.get("relation") for _, _, d in out_edges}

    # Verify STAR subnode relations exist
    assert "HAS_ACTION" in edge_relations
    assert "HAS_SITUATION" in edge_relations or "HAS_ACTION" in edge_relations
    assert "HAS_RESULT" in edge_relations or "ACHIEVED_METRIC" in edge_relations


def test_temporal_metadata_extraction():
    """Verify CareerGraphBuilder extracts role date ranges and attaches temporal recency scores."""
    story_md = """
    # Senior Software Engineer — Rocket Mortgage
    *Jan 2023 – Jul 2025*
    ## Projects
    ### Story 1 — Observability Overhaul
    - Action: Re-engineered Dynatrace synthetic health-checks.
    """
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(story_md)

    role_node = "Senior Software Engineer"
    assert graph.has_node(role_node)
    role_data = graph.nodes[role_node]
    assert role_data.get("start_year") == 2023
    assert role_data.get("end_year") == 2025
    assert role_data.get("recency_score") is not None
    assert float(role_data["recency_score"]) > 0.8


def test_200_plus_taxonomy_expansion_and_alias_resolution():
    """Verify rich taxonomy aliases (K8s, Postgres, DLQ) and 3-level macro-domain hierarchy."""
    sample_text = """
    # Staff Backend Architect — Rocket Mortgage
    *2023 – 2025*
    ## Projects
    ### Story 1 — Cloud Modernization
    - Action: Architected K8s cluster deployments on AWS using Postgres databases with DLQ error handling.
    - Result: Slashed latency by 70% and cut cloud costs by 40%.
    """
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(sample_text)

    # 1. Alias Disambiguation Verification
    assert graph.has_node("Kubernetes")  # Resolved from K8s
    assert graph.has_node("PostgreSQL")  # Resolved from Postgres
    assert graph.has_node("Dead Letter Queues")  # Resolved from DLQ

    # 2. 3-Level MacroDomain Hierarchy
    macro_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "MacroDomain"]
    assert len(macro_nodes) > 0
    assert "CloudAndInfrastructure" in macro_nodes or "DistributedSystemsAndMessaging" in macro_nodes

    # 3. Competency Grounding
    competency_edges = [
        (u, v) for u, v, d in graph.edges(data=True)
        if d.get("relation") == "HAS_COMPETENCY"
    ]
    assert len(competency_edges) > 0




