"""Stage 3: GraphRAG Tailoring & Strict 2-Page ATS PDF Rendering Package."""

from .career_graph_builder import CareerGraphBuilder
from .cover_letter import CoverLetterData, CoverLetterGenerator
from .fact_guard import FactGuard
from .graph_retriever import GraphRetriever
from .graph_vector_engine import GraphVectorEngine
from .outreach_drafter import OutreachDrafter
from .pdf_renderer import PdfRenderer, render_pdf_resume
from .pdf_styles import (
    AdaptivePageCanvas,
    PageCountCanvas,
    format_contact_paragraph,
    format_education_split,
    format_job_heading,
    format_job_heading_split,
    get_resume_styles,
    markdown_to_reportlab_html,
)
from .qa_generator import QAGenerator
from .resume_generator import ResumeGenerator
from .surgical_optimizer import SurgicalOptimizer

__all__ = [
    "CareerGraphBuilder",
    "GraphVectorEngine",
    "SurgicalOptimizer",
    "FactGuard",
    "GraphRetriever",
    "PdfRenderer",
    "render_pdf_resume",
    "get_resume_styles",
    "markdown_to_reportlab_html",
    "format_contact_paragraph",
    "format_job_heading",
    "format_job_heading_split",
    "format_education_split",
    "PageCountCanvas",
    "AdaptivePageCanvas",
    "CoverLetterGenerator",
    "CoverLetterData",
    "QAGenerator",
    "OutreachDrafter",
    "ResumeGenerator",
]
