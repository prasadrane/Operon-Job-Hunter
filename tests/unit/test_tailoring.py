"""Unit tests for Stage 3 Tailoring & PDF Generation Pipeline:
- SurgicalOptimizer (ATS keyword bolding, <20% character cap, max 3 phrases)
- FactGuard (anti-hallucination auditor against canonical master resume)
- GraphRetriever (STAR stories, verified metrics, tech stack retrieval)
- PdfStyles & PdfRenderer (ReportLab 2-page ATS PDF generation)
- CoverLetterGenerator (tailored cover letter markdown and PDF)
- QAGenerator (application open-ended question answering)
- OutreachDrafter (<=300 char recruiter/hiring manager LinkedIn notes)
- ResumeGenerator (full Stage 3 orchestration to TailoredArtifacts)
"""

import importlib
import json
import os
from pathlib import Path
import re
import pytest
from unittest.mock import MagicMock, patch

from src.core.models import JobPosting, JobStatus, TailoredArtifacts

# Dynamic imports
surgical_mod = importlib.import_module(
    "src.pipeline.3_tailoring.surgical_optimizer")
SurgicalOptimizer = surgical_mod.SurgicalOptimizer

fact_mod = importlib.import_module("src.pipeline.3_tailoring.fact_guard")
FactGuard = fact_mod.FactGuard

graph_mod = importlib.import_module("src.pipeline.3_tailoring.graph_retriever")
GraphRetriever = graph_mod.GraphRetriever

styles_mod = importlib.import_module("src.pipeline.3_tailoring.pdf_styles")
get_resume_styles = styles_mod.get_resume_styles
markdown_to_reportlab_html = styles_mod.markdown_to_reportlab_html
format_contact_paragraph = styles_mod.format_contact_paragraph
format_education_split = styles_mod.format_education_split
format_certification_split = styles_mod.format_certification_split
sanitize_ats_markdown = styles_mod.sanitize_ats_markdown
prevent_widow_words = styles_mod.prevent_widow_words

renderer_mod = importlib.import_module("src.pipeline.3_tailoring.pdf_renderer")
PdfRenderer = renderer_mod.PdfRenderer
compact_skills_for_1page = renderer_mod.compact_skills_for_1page
render_pdf_resume = renderer_mod.render_pdf_resume

cover_mod = importlib.import_module("src.pipeline.3_tailoring.cover_letter")
CoverLetterGenerator = cover_mod.CoverLetterGenerator
CoverLetterData = cover_mod.CoverLetterData

qa_mod = importlib.import_module("src.pipeline.3_tailoring.qa_generator")
QAGenerator = qa_mod.QAGenerator

outreach_mod = importlib.import_module(
    "src.pipeline.3_tailoring.outreach_drafter")
OutreachDrafter = outreach_mod.OutreachDrafter

resume_mod = importlib.import_module(
    "src.pipeline.3_tailoring.resume_generator")
ResumeGenerator = resume_mod.ResumeGenerator


# ============================================================================
# 1. SurgicalOptimizer Tests
# ============================================================================

def test_surgical_optimizer_bold_ratio_and_phrase_cap():
    optimizer = SurgicalOptimizer(bold_cap=0.15, max_bold_phrases=2, bold_impact_only=False)
    bullet = "Architected and deployed enterprise microservices using AWS ECS, Docker, Kafka, and .NET 8."
    keywords = ["AWS ECS", "Kafka", ".NET 8", "Docker", "microservices"]

    optimized = optimizer.inject_bold_tags(bullet, keywords)

    # At least one JD-matching keyword should be bolded
    bold_phrases = optimizer.extract_bold_phrases(optimized)
    assert len(bold_phrases) >= 1
    ratio = optimizer.calculate_bold_ratio(optimized)
    assert ratio <= 0.25  # within tolerance (0.15 cap + 0.10)

    # Check max 2 bold phrases (new tighter cap)
    assert len(bold_phrases) <= 2


def test_surgical_optimizer_prevents_first_word_bolding():
    """First word (action verb) not bolded. Impact metrics prioritized. JD tech bolded if slots remain."""
    optimizer = SurgicalOptimizer(allow_first_word_bold=False, bold_impact_only=True)
    # Bullet with 1 impact + 1 tech term to test priority ordering
    bullet = "Spearheaded cloud modernization to AWS ECS Fargate cutting infrastructure costs by 40%."
    keywords = ["AWS ECS Fargate"]

    optimized = optimizer.inject_bold_tags(bullet, keywords)
    # Action verb should NOT be bolded
    assert not optimized.startswith("<b>Spearheaded</b>")
    # Impact metric should be bolded (priority 1)
    assert "<b>40%</b>" in optimized
    # JD-matching tech SHOULD also be bolded (priority 2, 1 slot remains)
    assert "<b>AWS ECS Fargate</b>" in optimized


def test_surgical_optimizer_optimize_bullets_impact_only():
    optimizer = SurgicalOptimizer(bold_impact_only=True)
    bullets = [
        "Re-engineered Dynatrace synthetic monitoring to slash on-call alert noise by 80% and reclaim ~20 engineering hours monthly.",
        "Optimized SQL Server query execution plans to slash report latency from 45s to <3s and reduce peak CPU load by ~30%."
    ]
    optimized_bullets = optimizer.optimize_bullets(bullets)

    assert len(optimized_bullets) == 2
    # Tech not in keywords should NOT be bolded
    assert "<b>SQL Server</b>" not in optimized_bullets[1]
    assert "<b>Dynatrace</b>" not in optimized_bullets[0]
    # Ensure ratio is compliant (0.15 cap + 0.10 tolerance = 0.25)
    for b in optimized_bullets:
        assert optimizer.calculate_bold_ratio(b) <= 0.25


def test_surgical_optimizer_jd_tech_bold():
    """Tech terms in JD keywords get bolded when appearing in bullet."""
    optimizer = SurgicalOptimizer(allow_jd_tech_bold=True)
    bullet = "Built scalable distributed systems using Kubernetes and observability with Dynatrace."
    keywords = ["Kubernetes"]  # only Kubernetes in JD, not Dynatrace

    optimized = optimizer.inject_bold_tags(bullet, keywords=keywords)
    # Kubernetes IS in JD → should be bolded
    assert "<b>Kubernetes</b>" in optimized
    # Dynatrace NOT in JD → should NOT be bolded
    assert "<b>Dynatrace</b>" not in optimized


def test_surgical_optimizer_anchor_bold():
    """Anchor bold fires when no impact metrics found."""
    optimizer = SurgicalOptimizer(allow_anchor_bold=True, anchor_bold_words=3)
    bullet = "Led enterprise-wide migration of legacy monolith to cloud-native microservices architecture on AWS."

    optimized = optimizer.inject_bold_tags(bullet, keywords=[])
    # First 3 words should be bolded
    phrases = optimizer.extract_bold_phrases(optimized)
    assert len(phrases) == 1
    assert phrases[0].startswith("Led")


def test_surgical_optimizer_anchor_bold_skipped_when_impact_found():
    """Anchor bold skipped when impact metrics are present."""
    optimizer = SurgicalOptimizer(allow_anchor_bold=True, anchor_bold_words=3)
    bullet = "Led migration of legacy systems reducing infrastructure costs by 40%."

    optimized = optimizer.inject_bold_tags(bullet, keywords=[])
    # Impact metric should be bolded, NOT anchor
    phrases = optimizer.extract_bold_phrases(optimized)
    assert any("40%" in p for p in phrases)
    # First words should NOT be bolded (anchor skipped)
    assert not optimized.startswith("<b>Led")


def test_end_to_end_jd_mixed_tech_and_impact_bolding():
    """Realistic mixed JD: some tech in candidate's stack, some not.
    JD tech that matches bullet text gets bolded. JD tech NOT in bullet doesn't.
    Tech NOT in JD (even if in bullet) does NOT get bolded.
    Impact metrics always prioritized over tech.
    """
    extract_keywords = resume_mod.extract_keywords_from_text
    optimizer = SurgicalOptimizer()  # defaults: jd_tech=True, anchor=False, cap=0.15, max=2

    # --- Realistic mixed JD ---
    # Mentions: AWS, Kubernetes, Python, C# (in candidate's stack)
    # Also mentions: React, Go (NOT in COMMON_TECH_KEYWORDS → won't be extracted)
    # Also mentions: Docker, Terraform (in candidate's stack)
    jd_text = (
        "Senior Software Engineer role. You will build distributed systems using "
        "AWS, Kubernetes, Python, and C#. Experience with React and Go is a plus. "
        "You will containerize with Docker and manage infrastructure via Terraform. "
        "Strong understanding of microservices and CI/CD required."
    )
    keywords = extract_keywords(jd_text)
    # React and Go are NOT in COMMON_TECH_KEYWORDS so they won't be extracted
    assert "React" not in keywords
    assert "Go" not in keywords
    # These should be extracted
    for expected in ["AWS", "Kubernetes", "Python", "C#", "Docker", "Terraform", "Microservices", "CI/CD"]:
        assert expected in keywords, f"{expected} missing from keywords"

    # --- Candidate's resume bullets (mixed tech — some in JD, some not) ---
    bullets = [
        # Bullet 1: AWS + Kubernetes (both in JD) + impact metric
        "Architected microservices on AWS ECS and Kubernetes reducing latency by 40%.",
        # Bullet 2: C# in JD, .NET Core NOT in JD, impact metric
        "Engineered C# .NET Core services processing millions of financial transactions with zero ledger corruption.",
        # Bullet 3: React + Go — NEITHER in JD keywords → should NOT be bolded at all
        "Built React dashboards with Go backend services scaling to 500K users.",
        # Bullet 4: Docker + Terraform (both in JD) + impact metric
        "Automated CI/CD pipelines using Docker and Terraform cutting deployment time by 70%.",
        # Bullet 5: Python in JD + clear impact metric
        "Developed Python data pipelines ingesting events daily cutting processing time by 60%.",
    ]

    optimized = optimizer.optimize_bullets(bullets, keywords)
    assert len(optimized) == 5

    # --- Bullet 1: Impact "40%" + one JD tech (Kubernetes or AWS) ---
    phrases_1 = optimizer.extract_bold_phrases(optimized[0])
    assert len(phrases_1) <= 2
    # Impact metric must be bolded
    assert any("40%" in p for p in phrases_1), f"No impact in {phrases_1}"
    # At least one JD-matching tech should be bolded if slots remain
    # (if impact takes 1 slot, 1 tech can fit)
    bold_text_1 = optimized[0]
    # Kubernetes is in JD + in bullet → may be bolded
    # React/Go are NOT in JD → must NOT be bolded (they aren't even in this bullet)

    # --- Bullet 2: Impact "zero ledger corruption" + C# (in JD) ---
    phrases_2 = optimizer.extract_bold_phrases(optimized[1])
    assert len(phrases_2) <= 2
    assert any("zero ledger corruption" in p for p in phrases_2), f"No impact in {phrases_2}"
    # C# is in JD + in bullet → should be bolded if slot available
    # .NET Core is NOT in JD keywords → must NOT be bolded
    assert "<b>.NET Core</b>" not in optimized[1]
    assert "**.NET Core**" not in optimized[1]

    # --- Bullet 3: NO bolding — React and Go not in JD keywords ---
    phrases_3 = optimizer.extract_bold_phrases(optimized[2])
    assert len(phrases_3) == 0, f"Expected no bold but got {phrases_3} in: {optimized[2]}"
    assert "<b>React</b>" not in optimized[2]
    assert "<b>Go</b>" not in optimized[2]

    # --- Bullet 4: Impact "70%" + one of Docker/Terraform ---
    phrases_4 = optimizer.extract_bold_phrases(optimized[3])
    assert len(phrases_4) <= 2
    assert any("70%" in p for p in phrases_4), f"No impact in {phrases_4}"
    # Docker and Terraform both in JD — at least one should be bolded if slot remains
    # Both in bullet text, both in keywords
    bold_4 = optimized[3]
    docker_bolded = "<b>Docker</b>" in bold_4 or "**Docker**" in bold_4
    terraform_bolded = "<b>Terraform</b>" in bold_4 or "**Terraform**" in bold_4
    assert docker_bolded or terraform_bolded, f"Expected at least one JD tech bolded in: {bold_4}"

    # --- Bullet 5: Python in JD, impact metric expected ---
    phrases_5 = optimizer.extract_bold_phrases(optimized[4])
    assert len(phrases_5) <= 2
    bold_5 = optimized[4]
    python_bolded = "<b>Python</b>" in bold_5 or "**Python**" in bold_5
    has_impact = any("60%" in p for p in phrases_5)
    # Python is in JD + in bullet → should be bolded if slot available
    # "60%" matches IMPACT_PATTERNS → should be bolded
    assert python_bolded or has_impact, f"Expected Python or impact bolded in: {bold_5}"

    # --- Global: ratio <= 0.25 for all bullets ---
    for i, b in enumerate(optimized):
        ratio = optimizer.calculate_bold_ratio(b)
        assert ratio <= 0.25, f"Bullet {i} ratio {ratio:.3f} > 0.25: {b}"


# ============================================================================
# 2. FactGuard Tests
# ============================================================================

def test_fact_guard_validates_grounded_bullet():
    guard = FactGuard()
    bullet = "Architected AWS ECS Fargate microservices cutting infrastructure costs by 40%."
    is_valid, reason = guard.validate_bullet(bullet)
    assert is_valid is True
    assert "verified" in reason.lower()


def test_fact_guard_catches_unverified_technology():
    guard = FactGuard()
    bullet = "Engineered smart contracts on Ethereum using Solidity and Rust for decentralized finance."
    is_valid, reason = guard.validate_bullet(bullet)
    assert is_valid is False
    assert any(tech.lower() in reason.lower()
               for tech in ["solidity", "ethereum", "rust", "unverified"])


def test_fact_guard_catches_exorbitant_metrics():
    guard = FactGuard()
    bullet = "Managed $50 billion budget and generated $100 Billion revenue for global hedge fund."
    is_valid, reason = guard.validate_bullet(bullet)
    assert is_valid is False
    assert "exorbitant" in reason.lower() or "exceeds" in reason.lower()


def test_fact_guard_formal_claim_triples_verification():
    """Verify FactGuard decomposes claims into formal triples and checks homomorphism with knowledge graph."""
    guard = FactGuard()
    grounded_bullet = "Architected AWS ECS Fargate microservices cutting infrastructure costs by 40%."
    res_grounded = guard.verify_claim_triples(grounded_bullet)
    assert res_grounded["is_valid"] is True
    assert len(res_grounded["verified_triples"]) > 0
    assert len(res_grounded["violations"]) == 0

    hallucinated_bullet = "Engineered quantum encryption algorithms on Ethereum cutting latency by 99.999%."
    res_hallucinated = guard.verify_claim_triples(hallucinated_bullet)
    assert res_hallucinated["is_valid"] is False
    assert len(res_hallucinated["violations"]) > 0



def test_fact_guard_validate_resume():
    guard = FactGuard()
    clean_resume = (
        "Alex Rivera\n"
        "Architected AWS microservices with C# and .NET 8.\n"
        "Optimized SQL Server query performance reducing report latency from 45s to <3s."
    )
    is_valid, violations = guard.validate_resume(clean_resume)
    assert is_valid is True
    assert len(violations) == 0

    hallucinated_resume = (
        "Alex Rivera\n"
        "Built Web3 dApps using Vyper and Blockchain smart contracts."
    )
    is_valid, violations = guard.validate_resume(hallucinated_resume)
    assert is_valid is False
    assert len(violations) > 0


# ============================================================================
# 3. GraphRetriever Tests
# ============================================================================

def test_graph_retriever_evidence_and_stories(tmp_path):
    retriever = GraphRetriever("data/MASTER_RESUME.md")
    target_skills = ["AWS ECS", "Kafka", "Dynatrace"]

    evidence = retriever.retrieve_evidence(target_skills, max_evidence=4)
    assert len(evidence) > 0
    assert any(
        "AWS" in ev or "Dynatrace" in ev or "Kafka" in ev for ev in evidence)

    stories = retriever.retrieve_stories(target_skills, max_stories=3)
    assert len(stories) > 0
    assert "title" in stories[0] or "story_title" in stories[0] or "content" in stories[0]


def test_graph_retriever_extract_top_metrics():
    retriever = GraphRetriever("data/MASTER_RESUME.md")
    metrics = retriever.get_top_metrics()
    assert len(metrics) > 0
    assert any(
        "40%" in m or "70%" in m or "80%" in m or "99.95%" in m or "45s" in m for m in metrics)


def test_graph_retriever_verified_skills():
    retriever = GraphRetriever("data/MASTER_RESUME.md")
    skills = retriever.get_verified_skills()
    assert len(skills) > 0
    skills_str = " ".join(skills).lower()
    assert "c#" in skills_str or ".net" in skills_str
    assert "aws" in skills_str


def test_graph_retriever_all_18_stories_company_mapping():
    retriever = GraphRetriever("data/MASTER_RESUME.md")
    stories = retriever._parsed_stories
    assert len(stories) == 18

    expected_companies = {
        1: "Rocket Mortgage",
        2: "Rocket Mortgage",
        3: "Rocket Mortgage",
        4: "Rocket Mortgage",
        5: "Rocket Mortgage",
        6: "Rocket Mortgage",
        7: "Rocket Mortgage",
        8: "Rocket Mortgage",
        9: "Rocket Mortgage",
        10: "Rocket Mortgage",
        11: "Rocket Mortgage",
        12: "Rocket Mortgage",
        13: "London Computer Systems",
        14: "London Computer Systems",
        15: "London Computer Systems",
        16: "EXFO Electro-Optical Engineering",
        17: "EXFO Electro-Optical Engineering",
        18: "Tanish Infotech Solutions",
    }

    for story in stories:
        m = re.search(r"Story (\d+)", story["story_title"])
        assert m is not None, f"Unexpected story title: {story['story_title']}"
        story_num = int(m.group(1))
        expected_co = expected_companies[story_num]
        assert story["company"] == expected_co, (
            f"Story {story_num} expected company '{expected_co}', but got '{story['company']}'"
        )
        if story_num == 18:
            assert len(story["bullets"]) == 1
            assert not any("GraphRAG" in b or "Information Systems" in b for b in story["bullets"])



# ============================================================================
# 4. PdfStyles & PdfRenderer Tests
# ============================================================================

def test_pdf_styles_html_conversions():
    text = "Implemented **AWS ECS** with *Docker* and `FastAPI` [Portfolio](https://alexrivera.dev)"
    html = markdown_to_reportlab_html(text)
    assert "<b>AWS ECS</b>" in html
    assert "<i>Docker</i>" in html
    assert "<b>FastAPI</b>" in html
    assert '<a href="https://alexrivera.dev">' in html


def test_pdf_styles_handles_raw_html_bold_and_italic_tags():
    text = "Engineered backend REST <b>microservices</b> and <i>event handlers</i> with ASP<b>.NET</b>"
    html = markdown_to_reportlab_html(text)
    assert "<b>microservices</b>" in html
    assert "<i>event handlers</i>" in html
    assert "&lt;b&gt;" not in html
    assert "&lt;i&gt;" not in html


def test_pdf_styles_preserve_standard_markdown_emphasis():
    html = markdown_to_reportlab_html("**Bold** and *italic* with 2 < 3")

    assert "<b>Bold</b>" in html
    assert "<i>italic</i>" in html
    assert "2 &lt; 3" in html


def test_pdf_styles_education_preserves_emphasis_and_dates():
    left_html, right_html = format_education_split(
        "- **M.S. in Information Systems** — *University of Cincinnati*, Cincinnati, OH (2018 - 2019)"
    )

    assert "<b>M.S. in Information Systems</b>" in left_html
    assert "<i>University of Cincinnati</i>" in left_html
    assert "2018 - 2019" in right_html
    assert "*" not in left_html
    assert "*" not in right_html


def test_pdf_styles_education_formatting_edge_cases():
    cases = [
        # (Input string, expected degree, expected school, expected location, expected dates)
        (
            "- **M.S. in Information Systems**. University of Cincinnati, Cincinnati, OH (2018 - 2019)",
            "M.S. in Information Systems",
            "University of Cincinnati",
            "Cincinnati, OH",
            "2018 - 2019",
        ),
        (
            "- **B.E. in Electronics & Telecommunication** — Savitribai Phule Pune University, Pune, India (2009 – 2013)",
            "B.E. in Electronics & Telecommunication",
            "Savitribai Phule Pune University",
            "Pune, India",
            "2009 - 2013",
        ),
        (
            "- **B.S. in Computer Science** - UIUC, Urbana, IL (2014-2018) | GPA: 3.9/4.0",
            "B.S. in Computer Science",
            "UIUC",
            "Urbana, IL",
            "2014 - 2018",
        ),
        (
            "- **Ph.D. in Data Science**, MIT, Cambridge, MA (2020 - 2024)",
            "Ph.D. in Data Science",
            "MIT",
            "Cambridge, MA",
            "2020 - 2024",
        ),
        (
            "- M.S. in Artificial Intelligence, Carnegie Mellon University, Pittsburgh, PA (2021 - 2023)",
            "M.S. in Artificial Intelligence",
            "Carnegie Mellon University",
            "Pittsburgh, PA",
            "2021 - 2023",
        ),
    ]

    for raw_input, exp_deg, exp_school, exp_loc, exp_dates in cases:
        left_html, right_html = format_education_split(raw_input)
        assert "*" not in left_html, f"Asterisk leaked in left_html for: {raw_input}"
        assert "*" not in right_html, f"Asterisk leaked in right_html for: {raw_input}"
        if exp_deg:
            assert exp_deg in left_html
        if exp_school:
            assert exp_school in left_html
        if exp_loc:
            assert exp_loc in right_html
        if exp_dates:
            assert exp_dates in right_html


def test_sanitize_ats_markdown():
    raw = "<b>AWS ECS</b> with <i>Docker</i> & <strong>Kafka</strong> (2020—2023) — Rocket Mortgage"
    sanitized = sanitize_ats_markdown(raw)
    assert "**AWS ECS**" in sanitized
    assert "*Docker*" in sanitized
    assert "**Kafka**" in sanitized
    assert "2020 - 2023" in sanitized
    assert "<b>" not in sanitized
    assert "<strong>" not in sanitized


def test_prevent_widow_words():
    single_word = "Governance"
    assert prevent_widow_words(single_word) == "Governance"

    bullet = "Established enterprise-wide Kafka governance standards"
    no_widow = prevent_widow_words(bullet)
    assert no_widow.endswith("governance&nbsp;standards")


def test_format_certification_split_cases():
    cases = [
        (
            "- **[AWS Certified Cloud Practitioner](https://credly.com/123)** — Amazon Web Services *(Issued: Apr 2026 | Expires: Apr 2029)*",
            "AWS Certified Cloud Practitioner",
            "Amazon Web Services",
            "Issued: Apr 2026 | Expires: Apr 2029",
        ),
        (
            "- **CKA: Certified Kubernetes Administrator** - CNCF / Linux Foundation (2025)",
            "CKA: Certified Kubernetes Administrator",
            "CNCF / Linux Foundation",
            "2025",
        ),
        (
            "- Microsoft Certified: Azure Developer Associate",
            "Microsoft Certified: Azure Developer Associate",
            "",
            "",
        ),
    ]

    for raw, exp_title, exp_issuer, exp_dates in cases:
        left_html, right_html = format_certification_split(raw)
        assert "*" not in left_html, f"Asterisk leaked in left_html: {raw}"
        assert "*" not in right_html, f"Asterisk leaked in right_html: {raw}"
        if exp_title:
            assert exp_title in left_html
        if exp_issuer:
            assert exp_issuer in left_html
        if exp_dates:
            assert exp_dates in right_html


def test_pdf_styles_master_education_and_certifications_clean():
    renderer_module = importlib.import_module(
        "src.pipeline.3_tailoring.pdf_renderer")
    master_resume = Path("data/MASTER_RESUME.md").read_text(encoding="utf-8")
    parsed = renderer_module.parse_resume_markdown(master_resume)

    assert parsed.education
    for edu in parsed.education:
        left, right = format_education_split(edu)
        assert "*" not in left
        assert "*" not in right

    assert parsed.certifications
    for cert in parsed.certifications:
        left, right = format_certification_split(cert)
        assert "*" not in left
        assert "*" not in right


def test_pdf_renderer_produces_valid_2page_pdf(tmp_path):
    renderer = PdfRenderer()
    output_pdf = tmp_path / "Alex_Rivera_Resume.pdf"

    master_md_path = Path("./data/MASTER_RESUME.md")
    assert master_md_path.exists()

    pdf_path = renderer.render(
        resume_source=master_md_path,
        output_pdf_path=output_pdf,
        target_pages=2,
        keywords=["C#", "AWS", ".NET 8", "Kafka"]
    )

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000
    # Check PDF Magic Header
    header = pdf_path.read_bytes()[:5]
    assert header == b"%PDF-"


def test_pdf_renderer_1page_compact_mode(tmp_path):
    renderer = PdfRenderer()
    output_pdf = tmp_path / "Alex_Rivera_1Page.pdf"
    master_md_path = Path("./data/MASTER_RESUME.md")

    pdf_path = renderer.render(
        resume_source=master_md_path,
        output_pdf_path=output_pdf,
        target_pages=1,
        keywords=["AWS", ".NET Core"]
    )

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000


def test_compact_skills_for_1page_rules():
    raw_skills = [
        "**Languages**: C#, Python, TypeScript, SQL (T-SQL)",
        "**Frontend**: Angular (12–18), TypeScript, RxJS, NgRx",
        "**Data & Storage**: SQL Server, DynamoDB (Single-Table Design), PostgreSQL, MySQL, T-SQL, Query Plan Optimization, LanceDB (Vector DB)",
        "**Generative AI & LLM Systems**: Amazon Bedrock (Claude Sonnet), Prompt Engineering, Prompt Guardrails, Intent-to-API Routing, Structured JSON Outputs, GraphRAG, Vector Indexing, Pydantic, Claude Code, GitHub Copilot",
        "**Observability, Testing & DevOps**: Dynatrace, OpenTelemetry, Splunk, PagerDuty, CloudWatch, Synthetic Monitoring, Split.io, WinDbg, dotnet-dump, dotnet-counters, xUnit, Moq, Playwright, TDD, GitHub Actions, CircleCI, Jenkins",
    ]

    compacted = compact_skills_for_1page(raw_skills)

    # 1. Frontend dropped
    assert not any("Frontend" in line for line in compacted)
    # 2. AI & Observability merged
    assert any("AI & Observability" in line for line in compacted)
    # 3. Annotations stripped
    assert not any("Single-Table Design" in line for line in compacted)
    # 4. Capped at 10 items per line
    for line in compacted:
        if ":" in line:
            items = line.split(":", 1)[1].split(",")
            assert len(items) <= 10


# ============================================================================
# 5. CoverLetterGenerator Tests
# ============================================================================

def test_cover_letter_generation_and_pdf(tmp_path):
    generator = CoverLetterGenerator()
    data = generator.generate(
        company="Capital One",
        jd_text="Senior .NET Engineer to build high-throughput microservices in AWS ECS with Kafka.",
        candidate_name="Alex Rivera",
        role_title="Senior .NET Engineer"
    )

    assert data.candidate_name == "Alex Rivera"
    assert data.company_name == "Capital One"
    assert len(data.paragraphs) >= 3

    md_text = generator.render_markdown(data)
    assert "Capital One" in md_text
    assert "Alex Rivera" in md_text

    output_pdf = tmp_path / "Cover_Letter_CapitalOne.pdf"
    pdf_path = generator.render_pdf(data, output_pdf)
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 500
    assert pdf_path.read_bytes()[:5] == b"%PDF-"


# ============================================================================
# 6. QAGenerator Tests
# ============================================================================

def test_qa_generator_standard_questions():
    qa = QAGenerator()
    job = JobPosting(
        id="job_qa_1",
        company="Stripe",
        title="Staff Backend Engineer",
        url="https://stripe.com/jobs/1",
        description="Scaling high-throughput payment systems with 99.999% availability."
    )

    answers = qa.generate_answers(job)
    assert "why_us" in answers
    assert "technical_challenge" in answers
    assert "work_authorization" in answers
    assert "H-1B" in answers["work_authorization"]
    assert "Stripe" in answers["why_us"]


def test_qa_generator_custom_questions_mock_llm():
    mock_llm = MagicMock()
    mock_llm.generate.return_value = json.dumps({
        "Describe your experience with distributed event streaming": "Established enterprise Kafka governance at Rocket Mortgage with schema registries across 5 teams."
    })

    qa = QAGenerator(llm=mock_llm)
    job = JobPosting(
        id="job_qa_2",
        company="Fidelity",
        title="Lead .NET Engineer",
        url="https://fidelity.com/1"
    )

    custom_qs = ["Describe your experience with distributed event streaming"]
    answers = qa.generate_answers(job, custom_questions=custom_qs)
    assert "Describe your experience with distributed event streaming" in answers
    assert "Kafka" in answers["Describe your experience with distributed event streaming"]


def test_qa_generator_with_graph_retriever_grounding():
    """Verify QAGenerator uses GraphRetriever causal paths to ground custom screening answers."""
    mock_retriever = MagicMock()
    mock_retriever.retrieve_causal_paths.return_value = [{
        "company": "Rocket Mortgage",
        "action": "architected an enterprise Kafka event-driven pipeline",
        "metric": ["99.99% uptime", "40M+ daily events"],
        "reasoning_chain": "Kafka Match -> Action -> 99.99% uptime"
    }]

    # When LLM fails, falls back to grounded graph answer
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = Exception("LLM Timeout")

    qa = QAGenerator(llm=mock_llm, retriever=mock_retriever)
    job = JobPosting(id="j_qa_g", company="Stripe", title="Senior Backend Engineer", url="https://stripe.com/1")
    answers = qa.generate_answers(job, custom_questions=["Tell us about a time you worked with Kafka"])
    ans_text = answers["Tell us about a time you worked with Kafka"]
    assert "Rocket Mortgage" in ans_text
    assert "99.99% uptime" in ans_text


# ============================================================================
# 7. OutreachDrafter Tests
# ============================================================================

def test_outreach_drafter_length_under_300_chars():
    drafter = OutreachDrafter()
    job = JobPosting(
        id="job_outreach_1",
        company="Databricks",
        title="Senior Software Engineer",
        url="https://databricks.com/1"
    )

    note_recruiter = drafter.draft_recruiter_dm(job, recruiter_name="Alex")
    assert len(note_recruiter) <= 300
    assert "Databricks" in note_recruiter
    assert "Alex" in note_recruiter or "10+" in note_recruiter

    note_hm = drafter.draft_hiring_manager_dm(job, manager_name="Sarah")
    assert len(note_hm) <= 300
    assert "Databricks" in note_hm


def test_outreach_drafter_with_graph_retriever_causal_hook():
    """Verify OutreachDrafter weaves causal reasoning chains into LinkedIn notes."""
    mock_retriever = MagicMock()
    mock_retriever.retrieve_causal_paths.return_value = [{
        "tech": ["AWS ECS Fargate"],
        "metric": ["40% cloud cost reduction"],
        "reasoning_chain": "AWS ECS Match -> Migrated monolith -> 40% cost drop"
    }]

    drafter = OutreachDrafter(retriever=mock_retriever)
    job = JobPosting(id="j_out_g", company="Snowflake", title="Senior Platform Engineer", url="https://snowflake.com/1")
    note = drafter.draft_hiring_manager_dm(job, manager_name="David")
    assert len(note) <= 300
    assert "AWS ECS Fargate" in note
    assert "40% cloud cost reduction" in note




# ============================================================================
# 8. ResumeGenerator Orchestrator Tests
# ============================================================================

def test_resume_generator_orchestration_mock(tmp_path):
    mock_llm = MagicMock()
    # Mock LLM tailored summary & bullets response
    mock_llm.generate.return_value = json.dumps({
        "summary": "Senior Software Engineer with 10+ years experience in C#, .NET 8, and AWS ECS microservices.",
        "optimized_bullets": [
            "Architected AWS ECS Fargate microservices cutting query latency by 70% and cloud spend by 40%."
        ]
    })

    generator = ResumeGenerator(
        llm=mock_llm,
        artifacts_dir=str(tmp_path)
    )

    job = JobPosting(
        id="job_orch_1",
        company="Capital One",
        title="Senior .NET Engineer",
        url="https://capitalone.com/jobs/1",
        description="We are seeking a Senior .NET Engineer with AWS, Kafka, and microservices experience."
    )

    artifacts = generator.generate(job)

    assert isinstance(artifacts, TailoredArtifacts)
    assert artifacts.job_id == "job_orch_1"
    assert artifacts.resume_pdf_path is not None
    assert Path(artifacts.resume_pdf_path).exists()
    assert Path(artifacts.resume_pdf_path).name == "Alex_Rivera_Resume.pdf"
    assert artifacts.cover_letter_path is not None
    assert Path(artifacts.cover_letter_path).exists()
    assert Path(artifacts.cover_letter_path).name == "Cover_Letter.pdf"
    assert len(artifacts.qa_answers) > 0
    assert artifacts.linkedin_outreach is not None
    assert len(artifacts.linkedin_outreach) <= 300
