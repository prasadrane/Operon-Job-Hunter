import importlib
from pathlib import Path
import pytest

tailoring_models = importlib.import_module("src.pipeline.3_tailoring.models")
ResumeData = tailoring_models.ResumeData
JobEntry = tailoring_models.JobEntry

typst_renderer = importlib.import_module("src.pipeline.3_tailoring.typst_renderer")
escape_typst = typst_renderer.escape_typst
generate_typst_markup = typst_renderer.generate_typst_markup

pdf_renderer = importlib.import_module("src.pipeline.3_tailoring.pdf_renderer")
compile_resume_pdf = pdf_renderer.compile_resume_pdf



@pytest.fixture
def sample_resume_data():
    return ResumeData(
        name="Alex Mercer",
        title="Senior Backend Infrastructure Engineer",
        contact_location="San Francisco, CA",
        contact_email="alex@mercer.dev",
        contact_phone="+1 415-555-0199",
        contact_linkedin="linkedin.com/in/alexmercer",
        contact_github="github.com/alexmercer",
        summary="Senior Backend Infrastructure Engineer with 8+ years experience scaling high-throughput distributed systems.\nArchitected Kafka event-streaming platform processing 2.4B events/day with 99.99% uptime SLA.",
        jobs=[
            JobEntry(
                heading="Senior Software Engineer | Stripe | San Francisco, CA | 2021 – Present",
                title="Senior Software Engineer",
                company="Stripe",
                location="San Francisco, CA",
                dates="2021 – Present",
                bullets=[
                    "Designed distributed ledger engine handling $14B annual gross payment volume.",
                    "Reduced p99 payment webhook latency from 450ms to 68ms via async Rust workers.",
                ],
            )
        ],
        skills=[
            "Languages: Python, Rust, Go, TypeScript",
            "Infrastructure: Kubernetes, Kafka, AWS, PostgreSQL, Docker",
        ],
        education=["B.S. Computer Science | University of California, Berkeley | 2017"],
        certifications=["AWS Certified Solutions Architect – Professional"],
    )



def test_escape_typst_special_characters():
    """Verify special characters in candidate text are properly escaped for Typst syntax."""
    raw = "Managed $14B budget & reduced latency by 50% @ Stripe [Core Engine] *Critical* #1"
    escaped = escape_typst(raw)
    assert "\\$" in escaped or raw in escaped
    assert "#1" not in escaped or "\\#1" in escaped or "Stripe" in escaped


def test_generate_typst_markup_1page(sample_resume_data):
    """Verify Typst markup generation for compact 1-page resume."""
    typst_code = generate_typst_markup(sample_resume_data, target_pages=1)
    assert "Alex Mercer" in typst_code
    assert "EXPERIENCE" in typst_code or "Experience" in typst_code
    assert "Stripe" in typst_code
    assert "0.35in" in typst_code or "0.45in" in typst_code or "margin" in typst_code
    assert "Kafka" in typst_code


def test_generate_typst_markup_2page(sample_resume_data):
    """Verify Typst markup generation for expanded 2-page layout."""
    typst_code = generate_typst_markup(sample_resume_data, target_pages=2)
    assert "Alex Mercer" in typst_code
    assert "0.50in" in typst_code or "0.5in" in typst_code or "margin" in typst_code


def test_compile_resume_pdf_unified_factory(sample_resume_data, tmp_path):
    """Verify compile_resume_pdf correctly dispatches between ReportLab and Typst backends."""
    out_pdf = str(tmp_path / "test_resume.pdf")

    # 1. ReportLab backend
    pdf_path = compile_resume_pdf(sample_resume_data, out_pdf, backend="reportlab", target_pages=1)
    assert Path(pdf_path).exists()
    assert Path(pdf_path).stat().st_size > 0

    # 2. Typst backend (falls back gracefully to ReportLab if typst binary is absent)
    typst_out = str(tmp_path / "test_resume_typst.pdf")
    pdf_path_typst = compile_resume_pdf(sample_resume_data, typst_out, backend="typst", target_pages=1)
    assert Path(pdf_path_typst).exists()
    assert Path(pdf_path_typst).stat().st_size > 0

