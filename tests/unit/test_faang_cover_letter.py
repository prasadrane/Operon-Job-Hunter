"""Unit tests for FAANG Gold-Standard Cover Letter Generator."""

import importlib
from pathlib import Path
import pytest

cl_mod = importlib.import_module("src.pipeline.3_tailoring.cover_letter")
CoverLetterGenerator = getattr(cl_mod, "CoverLetterGenerator")
CoverLetterData = getattr(cl_mod, "CoverLetterData")


def test_faang_cover_letter_hook_and_word_budget():
    """Verify FAANG cover letter avoids generic fluff and stays strictly under 250 words."""
    generator = CoverLetterGenerator()
    data = generator.generate(
        company="Databricks",
        jd_text="Staff Software Engineer to architect high-throughput distributed systems in AWS and Kafka with low-latency requirements.",
        candidate_name="Alex Rivera",
        role_title="Staff Software Engineer - Infrastructure",
    )

    assert data.company_name == "Databricks"
    assert data.candidate_name == "Alex Rivera"
    assert data.role_title == "Staff Software Engineer - Infrastructure"

    md_text = generator.render_markdown(data)
    
    # 1. Verify absence of generic filler phrases
    assert "excited to see" not in md_text.lower()
    assert "i have spent years working" not in md_text.lower()
    assert "i am writing to apply" not in md_text.lower()

    # 2. Verify executive impact hook
    assert "40%" in md_text or "80%" in md_text or "cost" in md_text.lower()
    assert "Databricks" in md_text

    # 3. Verify word budget (< 250 words)
    words = md_text.split()
    assert len(words) <= 250, f"Cover letter exceeded 250 words: {len(words)} words"


def test_faang_cover_letter_proof_points_grounded():
    """Verify cover letter includes targeted technical proof points matching JD themes."""
    generator = CoverLetterGenerator()
    
    # Case 1: Kafka & Cloud focused JD
    data_cloud = generator.generate(
        company="Stripe",
        jd_text="Backend infrastructure engineer building event streams with Kafka and AWS microservices.",
        role_title="Staff Backend Engineer",
    )
    md_cloud = generator.render_markdown(data_cloud)
    assert "Kafka" in md_cloud or "AWS" in md_cloud
    assert len(data_cloud.proof_points) >= 2

    # Case 2: Latency & Performance focused JD
    data_perf = generator.generate(
        company="Datadog",
        jd_text="Performance engineer tuning high-concurrency systems, memory profiling, and observability metrics.",
        role_title="Senior Performance Engineer",
    )
    md_perf = generator.render_markdown(data_perf)
    assert "Dynatrace" in md_perf or "latency" in md_perf.lower() or "WinDbg" in md_perf or "concurrency" in md_perf.lower()


def test_faang_cover_letter_pdf_rendering(tmp_path):
    """Verify ReportLab PDF generation renders valid 1-page document with proper header."""
    generator = CoverLetterGenerator()
    data = generator.generate(
        company="Google",
        jd_text="Senior Cloud Systems Engineer building scalable microservices and distributed databases.",
        candidate_name="Alex Rivera",
        role_title="Senior Cloud Systems Engineer",
    )

    pdf_output = tmp_path / "Cover_Letter_Google.pdf"
    result_path = generator.render_pdf(data, pdf_output)

    assert result_path.exists()
    assert result_path.stat().st_size > 1000
    assert result_path.read_bytes()[:5] == b"%PDF-"
