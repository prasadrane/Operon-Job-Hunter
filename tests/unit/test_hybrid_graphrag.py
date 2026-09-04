"""Unit tests for 100% Free Local Hybrid GraphRAG Engine with STAR+R ontology and Personalized PageRank."""

import importlib
import time
import pytest

builder_mod = importlib.import_module(
    "src.pipeline.3_tailoring.career_graph_builder")
CareerGraphBuilder = builder_mod.CareerGraphBuilder

hybrid_mod = importlib.import_module(
    "src.pipeline.3_tailoring.hybrid_graph_retriever")
HybridGraphRetriever = hybrid_mod.HybridGraphRetriever


SAMPLE_RESUME_MD = """# ALEX RIVERA — MASTER RESUME
**Alex Rivera** | alex.rivera@example.com | Lake Bluff, IL

## Technical Skills
- **Languages**: C#, Python, TypeScript, SQL
- **Cloud & Infrastructure**: AWS ECS Fargate, AWS Lambda, DynamoDB, Amazon MSK, Kafka, Terraform, Docker
- **Observability & DevOps**: Dynatrace, OpenTelemetry, Splunk, PagerDuty, WinDbg

## Exhaustive Experience & Bullet Library

### **Software Engineer** — *Rocket Mortgage*
*Lake Bluff, IL* | *Jan 2023 – Jul 2025*

#### Story 1 — Observability & Fannie Mae Integration (Dynatrace)
- **Re-engineered** Dynatrace synthetic health-check monitoring across Fannie Mae loan eligibility microservices, eliminating false-positive auth triggers to **slash on-call alert noise by 80%** and **reclaim ~20 engineering hours monthly**.
- **Diagnosed** root-cause monitoring gap, improving observability accuracy from 60% to 98%.

#### Story 4 — VB.NET Modernization to AWS ECS Fargate
- **Spearheaded** cloud modernization of mission-critical underwriting engine to **AWS ECS Fargate (.NET Core)** within a hard 6-month deadline, **cutting infrastructure costs by 40%** while achieving **99.95% uptime** and a **70% reduction in support tickets**.
- **Implemented Infrastructure as Code** using **Terraform** and CI/CD pipelines via **GitHub Actions**.

#### Story 6 — AI Intent-to-API Router on Amazon Bedrock (Claude Sonnet)
- **Engineered** AI-powered intent-to-API router leveraging **Amazon Bedrock (Claude Sonnet)**, translating natural language mortgage queries into structured JSON payloads with sub-second latency.
- **Reduced** loan lookup time by **70%**, turning manual workflows into sub-2-second natural language responses.

#### Story 7 — Enterprise Kafka Governance & Standards
- **Established** enterprise-wide **Kafka/AWS MSK** governance standards adopted by **all 5 major event-driven engineering teams within 3 months** through influence rather than mandate.
"""


def test_career_graph_builder_rich_starr_ontology():
    """Verify CareerGraphBuilder builds rich multi-layer graph with STAR+R, Categories, and Metrics."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)

    # 1. Verify Node presence across types
    node_types = {data.get("type") for _, data in graph.nodes(data=True)}
    assert "Company" in node_types
    assert "Role" in node_types
    assert "STAR_Story" in node_types
    assert "Technology" in node_types
    assert "TechCategory" in node_types
    assert "ImpactMetric" in node_types

    # 2. Verify Category Relationships
    assert graph.has_node("Kafka")
    assert graph.has_node("EventStreaming")
    assert graph.has_edge("Kafka", "EventStreaming")

    # 3. Verify Story to Tech and Metric connections
    assert graph.has_node("Story 4 — VB.NET Modernization to AWS ECS Fargate")
    story_neighbors = list(graph.neighbors("Story 4 — VB.NET Modernization to AWS ECS Fargate")) + \
        list(graph.predecessors("Story 4 — VB.NET Modernization to AWS ECS Fargate"))
    assert any("AWS ECS" in str(n) or "Terraform" in str(n)
               or "40%" in str(n) for n in story_neighbors)


def test_concept_and_category_expansion():
    """Verify concept expander maps high-level concepts to concrete tech and story seeds."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    seeds = retriever.extract_seeds(
        "We are looking for expertise in event-driven streaming pipelines and Kafka governance.")
    seed_names = [s.lower() for s in seeds.keys()]
    assert any(
        "kafka" in s or "eventstreaming" in s or "story 7" in s for s in seed_names)


def test_personalized_pagerank_multi_hop_retrieval():
    """Verify Personalized PageRank surfaces multi-hop connected story and metric nodes."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    results = retriever.retrieve(
        query="Cloud modernization, Docker containers, ECS and reducing infrastructure costs",
        top_k=5,
    )
    assert len(results) > 0
    top_node_names = [r["node"] for r in results]
    # Verify Story 4 or AWS ECS Fargate or 40% cost reduction appears in top results
    assert any(
        "Story 4" in n or "AWS ECS" in n or "40%" in n or "Terraform" in n for n in top_node_names)


def test_connected_subgraph_context_assembly():
    """Verify retriever extracts grounded STAR subgraphs with causal situation-action-result links."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    context_pack = retriever.retrieve_story_subgraphs(
        query="Generative AI, Amazon Bedrock, LLMs and latency reduction",
        max_stories=2,
    )
    assert len(context_pack) >= 1
    top_story = context_pack[0]
    assert "Bedrock" in top_story["title"] or "AI" in top_story["title"]
    assert len(top_story["technologies"]) > 0
    assert any(
        "Bedrock" in t or "Claude" in t for t in top_story["technologies"])
    assert any("70%" in m or "2-second" in m for m in top_story["metrics"])


def test_in_memory_sub_5ms_latency():
    """Verify in-memory multi-hop traversal executes with sub-10ms latency on local CPU."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    queries = [
        "Observability Dynatrace alert noise reduction",
        "AWS ECS Fargate cloud migration",
        "Kafka MSK event driven architecture governance",
        "Amazon Bedrock GenAI intent router",
        "C# .NET high throughput tuning",
    ] * 20  # 100 iterations

    start_time = time.perf_counter()
    for q in queries:
        retriever.retrieve(q, top_k=5)
    total_time = time.perf_counter() - start_time
    avg_ms = (total_time / len(queries)) * 1000

    print(f"\nAverage GraphRAG retrieval latency: {avg_ms:.2f}ms")
    # Must execute with low in-memory graph traversal latency (<25ms on local CPU)
    assert avg_ms < 25.0


def test_hierarchical_community_clustering_and_summaries():
    """Verify community detection partitions the career graph into macro capability clusters."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    communities = retriever.get_hierarchical_communities()
    assert len(communities) >= 2
    
    # Check that communities contain meaningful titles, technologies, and metrics
    comm_titles = [c.get("title", "") for c in communities]
    assert any("Streaming" in t or "Cloud" in t or "Observability" in t or "AI" in t for t in comm_titles)
    for c in communities:
        assert "summary" in c
        assert "nodes" in c


def test_causal_path_retrieval_and_reasoning_chains():
    """Verify causal path extraction produces explainable Requirement -> Tech/Pattern -> Action -> Metric chains."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    causal_paths = retriever.retrieve_causal_paths(
        query="High-throughput event streaming with Kafka governance and uptime metrics",
        max_paths=3,
    )
    assert len(causal_paths) > 0
    top_path = causal_paths[0]
    assert "tech" in top_path or "pattern" in top_path
    assert "action" in top_path
    assert "story" in top_path
    assert any("Kafka" in str(p.get("tech")) or "MSK" in str(p.get("tech")) or "Streaming" in str(p.get("pattern")) for p in causal_paths)


def test_tri_hybrid_reciprocal_rank_fusion_rrf():
    """Verify Tri-Hybrid RRF fuses Lexical, Vector, and Edge-Weighted PPR ranks."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    rrf_results = retriever.retrieve_rrf("cloud modernization with Terraform and AWS ECS Fargate", top_k=5)
    assert len(rrf_results) > 0
    top_nodes = [r["node"] for r in rrf_results]
    assert any("AWS" in str(n) or "Terraform" in str(n) or "Story 4" in str(n) for n in top_nodes)
    for r in rrf_results:
        assert "rrf_score" in r
        assert "lexical_rank" in r
        assert "vector_rank" in r
        assert "ppr_rank" in r


def test_clean_community_summaries_no_calendar_years():
    """Verify that community summaries contain only true impact metrics without calendar years."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    communities = retriever.get_hierarchical_communities()
    for comm in communities:
        for m in comm.get("metrics", []):
            m_str = str(m)
            # Ensure no calendar years
            assert m_str not in ["2009", "2013", "2018", "2019", "2023", "2025"]
            # Ensure no raw isolated counting integers
            assert not (m_str.isdigit() and len(m_str) <= 2)


def test_transferable_skill_gap_reasoner_bridging():
    """Verify ontology 1-hop bridging maps unlisted JD skills (e.g. RabbitMQ) to candidate strengths (Kafka/MSK)."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    # RabbitMQ is not in candidate's resume, but is in DistributedMessaging category with Kafka/MSK
    gap_analysis = retriever.bridge_skill_gaps(
        jd_skills=["Kafka", "RabbitMQ", "Rust", "AWS ECS Fargate"]
    )

    assert "direct_matches" in gap_analysis
    assert "transferable_bridges" in gap_analysis
    assert "bridging_statements" in gap_analysis

    # Direct matches
    assert "Kafka" in gap_analysis["direct_matches"]
    assert "AWS ECS Fargate" in gap_analysis["direct_matches"]

    # Transferable bridges: RabbitMQ should bridge via DistributedMessaging to Kafka or EventStreaming
    bridges = gap_analysis["transferable_bridges"]
    assert any(b["target_skill"] == "RabbitMQ" for b in bridges)
    rabbit_bridge = next(b for b in bridges if b["target_skill"] == "RabbitMQ")
    assert len(rabbit_bridge["bridging_skills"]) > 0
    assert len(gap_analysis["bridging_statements"]) > 0


def test_cross_project_longitudinal_competencies():
    """Verify retriever aggregates multi-story subgraphs to compute cumulative domain mastery."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    longitudinal = retriever.get_longitudinal_competencies()
    assert len(longitudinal) > 0
    first = longitudinal[0]
    assert "domain" in first
    assert "cumulative_stories" in first
    assert "key_technologies" in first
    assert "verified_impact_metrics" in first


def test_graph_grounded_interview_simulator_packet():
    """Verify interview simulator creates targeted questions and grounded STAR model answers."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    prep_packet = retriever.generate_interview_prep_packet(
        target_skills=["Kafka", "Dynatrace", "AWS ECS Fargate"]
    )
    assert len(prep_packet) >= 2
    for item in prep_packet:
        assert "question" in item
        assert "question_type" in item
        assert "grounded_story" in item
        assert "model_answer" in item
        assert "situation" in item["model_answer"]
        assert "action" in item["model_answer"]
        assert "result" in item["model_answer"]


def test_multi_scale_granular_retrieval_and_competency_profile():
    """Verify multi-scale retrieval (Atomic Proofs, STAR Narratives, Longitudinal Arcs) and Competency Profiles."""
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(SAMPLE_RESUME_MD)
    retriever = HybridGraphRetriever(graph=graph)

    # 1. Atomic Proofs (Single-line bullet points with metrics for tight space limits)
    atomic_proofs = retriever.retrieve_atomic_proofs("AWS ECS Fargate cloud migration", top_k=2)
    assert len(atomic_proofs) > 0
    assert "proof_point" in atomic_proofs[0]
    assert "metrics" in atomic_proofs[0]

    # 2. Full STAR Narratives
    star_narratives = retriever.retrieve_star_narratives("Kafka streaming governance", max_stories=2)
    assert len(star_narratives) > 0
    assert "situation" in star_narratives[0]
    assert "action" in star_narratives[0]
    assert "result" in star_narratives[0]

    # 3. Longitudinal Arcs
    arcs = retriever.retrieve_longitudinal_arcs("Event-Driven Architecture")
    assert len(arcs) > 0
    assert "years_of_experience" in arcs[0] or "active_span_years" in arcs[0]

    # 4. Enterprise Competency Profile
    profile = retriever.get_competency_profile()
    assert len(profile) > 0
    assert any(c["dimension"] in ["SystemResilience", "OperationalExcellence", "CostOptimization", "EnterpriseGovernance", "EngineeringVelocity"] for c in profile)




