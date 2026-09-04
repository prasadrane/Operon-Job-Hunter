"""Unit tests for Phase 3 Recruiter Discovery & Cold Outreach Agent:
- RecruiterFinder (hiring manager discovery, boolean search queries, graph-intersection matching)
- EmailDrafter (FactGuard STAR hook verification, <150 word email draft, dual Email/InMail generation, draft-only safety)
"""

import importlib
import pytest
import networkx as nx

from src.agents.outreach.recruiter_finder import RecruiterFinder
from src.agents.outreach.email_drafter import EmailDrafter, OutreachDraft

# Dynamic imports for numbered package directory
fact_mod = importlib.import_module("src.pipeline.3_tailoring.fact_guard")
FactGuard = fact_mod.FactGuard

graph_builder_mod = importlib.import_module("src.pipeline.3_tailoring.career_graph_builder")
CareerGraphBuilder = graph_builder_mod.CareerGraphBuilder


# ============================================================================
# 1. Personalized Email Drafting & Length Cap (<150 words) Tests
# ============================================================================

def test_personalized_recruiter_outreach_drafting():
    """Verify basic recruiter outreach draft contains company, role, STAR hook, and is <150 words."""
    drafter = EmailDrafter()
    email = drafter.draft_outreach(
        company="Netflix",
        role="Senior Distributed Systems Engineer",
        star_hook="scaled Kafka streaming to 10M+ events/day with 99.99% uptime at Rocket Mortgage",
    )
    assert "Netflix" in email
    assert "10M+ events/day" in email
    assert "Senior Distributed Systems Engineer" in email
    assert len(email.split()) < 150  # Strict cold email rule (<150 words)


def test_outreach_draft_with_recipient_and_candidate_name():
    """Verify personalization with specific hiring manager name and candidate signature."""
    drafter = EmailDrafter()
    email = drafter.draft_outreach(
        company="Stripe",
        role="Staff Infrastructure Engineer",
        star_hook="led AWS cloud migration cutting infrastructure latency by 40%",
        recipient_name="Sarah Connor",
        candidate_name="Alex Mercer",
    )
    assert "Sarah" in email or "Sarah Connor" in email
    assert "Stripe" in email
    assert "Alex Mercer" in email
    assert len(email.split()) < 150


# ============================================================================
# 2. FactGuard Validation Tests
# ============================================================================

def test_email_drafter_factguard_passes_verified_claim():
    """Verify that verified claims pass FactGuard validation cleanly."""
    fact_guard = FactGuard()
    drafter = EmailDrafter(fact_guard=fact_guard)
    
    verified_hook = "scaled Kafka event streaming to 10M+ events/day at Rocket Mortgage"
    draft = drafter.draft_dual_outreach(
        company="Uber",
        role="Senior Backend Engineer",
        star_hook=verified_hook,
    )
    assert draft.verified is True
    assert "Uber" in draft.email
    assert len(draft.email.split()) < 150


def test_email_drafter_factguard_blocks_unverified_hallucinations():
    """Verify that unverified/hallucinated tech claims (e.g. Solidity/Web3/Blockchain) are blocked."""
    fact_guard = FactGuard()
    drafter = EmailDrafter(fact_guard=fact_guard)
    
    unverified_hook = "engineered Solidity smart contracts on Ethereum blockchain with Web3"
    with pytest.raises(ValueError, match="FactGuard validation failed"):
        drafter.draft_outreach(
            company="Coinbase",
            role="Protocol Engineer",
            star_hook=unverified_hook,
        )


def test_email_drafter_factguard_graph_backed_validation():
    """Verify FactGuard with dynamic NetworkX candidate graph validates claims."""
    builder = CareerGraphBuilder()
    resume_text = """
    # Senior Software Engineer — Rocket Mortgage
    ### Distributed Streaming
    - Architected Kafka event streaming platform handling 10M+ daily events with 99.99% uptime.
    - Optimized C# and AWS services reducing compute latency by 35%.
    """
    graph = builder.build_from_text(resume_text)
    fact_guard = FactGuard(graph=graph)
    drafter = EmailDrafter(fact_guard=fact_guard)

    # Valid graph tech
    valid_email = drafter.draft_outreach(
        company="Databricks",
        role="Data Infrastructure Engineer",
        star_hook="scaled Kafka streaming pipelines processing 10M+ daily events",
    )
    assert "Databricks" in valid_email

    # Invalid unverified tech
    with pytest.raises(ValueError, match="FactGuard validation failed"):
        drafter.draft_outreach(
            company="Polygon Labs",
            role="Core Dev",
            star_hook="built Rust smart contract protocols on Solana and Polygon",
        )


# ============================================================================
# 3. Dual Output Generation (Email + LinkedIn InMail Snippet)
# ============================================================================

def test_dual_format_generation_email_and_inmail():
    """Verify EmailDrafter generates both Email format and concise LinkedIn InMail snippet."""
    drafter = EmailDrafter()
    drafts = drafter.draft_dual_outreach(
        company="Spotify",
        role="Backend Engineer - Audio Streaming",
        star_hook="architected high-throughput Kafka streaming services processing 10M+ daily events",
        recipient_name="David",
        candidate_name="Jane Doe",
    )
    
    assert isinstance(drafts, OutreachDraft)
    assert drafts.email is not None
    assert drafts.inmail is not None
    assert "Spotify" in drafts.email
    assert "Spotify" in drafts.inmail
    assert len(drafts.email.split()) < 150
    # InMail must be concise (e.g. <= 80 words, <= 500 chars)
    assert len(drafts.inmail.split()) <= 80
    assert len(drafts.inmail) <= 500
    assert "Kafka" in drafts.inmail


# ============================================================================
# 4. Graph-Intersection Matching Tests (RecruiterFinder)
# ============================================================================

def test_recruiter_finder_hiring_manager_keywords():
    """Verify RecruiterFinder generates targeted hiring manager & recruiter search keywords."""
    finder = RecruiterFinder()
    keywords = finder.find_hiring_manager_keywords("Senior Distributed Systems Engineer")
    
    assert len(keywords) > 0
    assert any("Engineering Manager" in kw or "Director" in kw or "Lead" in kw for kw in keywords)
    assert any("Recruiter" in kw or "Talent" in kw or "Sourcing" in kw for kw in keywords)


def test_recruiter_finder_search_queries():
    """Verify RecruiterFinder builds effective boolean search queries for LinkedIn."""
    finder = RecruiterFinder()
    queries = finder.generate_search_queries("Apple", "Senior Machine Learning Engineer")
    
    assert len(queries) > 0
    assert any("Apple" in q for q in queries)
    assert any("Machine Learning" in q or "Engineering Manager" in q for q in queries)


def test_recruiter_finder_graph_intersection_matching():
    """Verify graph-intersection matching between target JD tech keywords and candidate career graph."""
    builder = CareerGraphBuilder()
    resume_text = """
    # Staff Software Engineer — Rocket Mortgage
    ### Real-Time Financial Data Pipeline
    - Designed Kafka and AWS ECS streaming microservices in C# handling 10M+ daily events.
    - Integrated Redis caching and PostgreSQL database for sub-10ms query performance.
    - Led Docker containerization and Kubernetes orchestration for zero-downtime deployments.
    """
    candidate_graph = builder.build_from_text(resume_text)
    finder = RecruiterFinder()

    jd_keywords = ["Kafka", "AWS", "Kubernetes", "Rust", "Solidity", "GraphQL", "Redis"]
    
    intersection = finder.match_graph_intersection(
        jd_keywords=jd_keywords,
        candidate_graph=candidate_graph,
    )
    
    # Intersecting skills should contain candidate's verified tech that matches JD
    matched_techs = [item["technology"] for item in intersection]
    matched_kws = [item["matched_keyword"] for item in intersection]
    assert "Kafka" in matched_techs or "Kafka" in matched_kws
    assert "AWS" in matched_techs or "AWS ECS" in matched_techs or "AWS" in matched_kws
    assert "Redis" in matched_techs or "Kubernetes" in matched_techs
    # Unverified JD skills should not be in intersection
    assert "Solidity" not in matched_techs and "Solidity" not in matched_kws
    assert "Rust" not in matched_techs and "Rust" not in matched_kws


    # Each match should include associated project context or relations
    for item in intersection:
        assert "technology" in item
        assert "projects" in item
        assert isinstance(item["projects"], list)


def test_recruiter_finder_recommend_star_hook():
    """Verify RecruiterFinder recommends the best STAR hook based on graph intersection."""
    builder = CareerGraphBuilder()
    resume_text = """
    # Senior Distributed Systems Engineer — Rocket Mortgage
    ### Core Event Streaming
    - Scaled Kafka event streaming to 10M+ daily events with 99.99% uptime.
    - Engineered AWS microservices reducing operational costs by 30%.
    """
    candidate_graph = builder.build_from_text(resume_text)
    finder = RecruiterFinder()

    best_hook = finder.recommend_star_hook(
        target_role="Kafka Infrastructure Engineer",
        jd_keywords=["Kafka", "Streaming", "Distributed Systems"],
        candidate_graph=candidate_graph,
    )
    assert "Kafka" in best_hook or "10M+" in best_hook or "streaming" in best_hook.lower()


# ============================================================================
# 5. Draft-Only Safety Flag Verification Tests
# ============================================================================

def test_draft_only_safety_flag_enforcement():
    """Verify that dispatching in draft_only=True mode strictly blocks sending and saves draft."""
    drafter = EmailDrafter()
    draft = drafter.draft_dual_outreach(
        company="DoorDash",
        role="Backend Infrastructure Engineer",
        star_hook="scaled Kafka streaming to 10M+ events/day",
    )
    
    # Default dispatch with draft_only=True
    result = drafter.dispatch_outreach(draft, draft_only=True)
    assert result["dispatched"] is False
    assert result["status"] == "DRAFT_SAVED"
    assert "draft_only" in result["mode"] or result["mode"] == "DRAFT_ONLY"
    assert result["draft"] is not None


def test_draft_only_flag_default_is_true():
    """Verify safety default is draft_only=True."""
    drafter = EmailDrafter()
    draft = drafter.draft_dual_outreach(
        company="DoorDash",
        role="Backend Infrastructure Engineer",
        star_hook="scaled Kafka streaming to 10M+ events/day",
    )
    # Calling dispatch_outreach without specifying draft_only must default to True
    result = drafter.dispatch_outreach(draft)
    assert result["dispatched"] is False
    assert result["status"] == "DRAFT_SAVED"
