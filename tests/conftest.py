"""Shared pytest configuration.

1. Environment isolation: some tests (e.g. the CLI demo) set process-wide
   environment variables such as PRIMARY_LLM_PROVIDER. Without restoring them,
   later tests see a polluted environment and fail depending on run order.
2. Private-corpus tests: a handful of tests assert against the author's full,
   private career corpus (data/MASTER_RESUME.md and data/MASTER_RESUME.jsonl),
   which is gitignored. They are skipped when that corpus is absent, e.g. in
   CI or a fresh clone.
"""

import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

_PRIVATE_CORPUS_TESTS = {
    "tests/unit/test_tailoring.py": {
        "test_graph_retriever_evidence_and_stories",
        "test_graph_retriever_extract_top_metrics",
        "test_graph_retriever_verified_skills",
        "test_graph_retriever_all_18_stories_company_mapping",
        "test_pdf_styles_master_education_and_certifications_clean",
        "test_pdf_renderer_produces_valid_2page_pdf",
        "test_pdf_renderer_1page_compact_mode",
    },
    "tests/unit/test_brain_synth_driver.py": {
        "test_qa_facets_expand_past_gate",
        "test_fact_banks_cover_corpus_node_types",
        "test_qa_facet_capacity_reaches_gate",
        "test_qa_facet_jobs_carry_stable_wid",
    },
}


def _private_corpus_present() -> bool:
    return (_REPO_ROOT / "data" / "MASTER_RESUME.md").exists() and (
        _REPO_ROOT / "data" / "MASTER_RESUME.jsonl"
    ).exists()


def pytest_collection_modifyitems(config, items):
    if _private_corpus_present():
        return
    skip = pytest.mark.skip(
        reason="requires the private, gitignored data/MASTER_RESUME.{md,jsonl} corpus"
    )
    for item in items:
        rel = Path(str(item.fspath)).resolve().relative_to(_REPO_ROOT).as_posix()
        if item.originalname in _PRIVATE_CORPUS_TESTS.get(rel, ()):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _restore_environ():
    saved = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)
        try:
            from src.core.config import get_settings

            get_settings.cache_clear()
        except Exception:
            pass
