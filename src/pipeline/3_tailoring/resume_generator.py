"""Stage 3: GraphRAG Resume Generator & Artifact Orchestrator.

Coordinates:
1. Keyword extraction & GraphRAG story retrieval
2. LLM / Heuristic summary & bullet tailoring
3. Surgical ATS keyword bolding (<20% cap)
4. FactGuard anti-hallucination validation
5. ReportLab strict 2-page PDF rendering
6. Cover letter generation (text + PDF)
7. Application form Q&A generation
8. Recruiter LinkedIn outreach drafting
Produces unified `TailoredArtifacts`.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from src.core.config import get_settings
from src.core.gateway.facade import LLMGateway, get_gateway
from src.core.memory.core_memory_manager import CoreMemoryManager
from src.core.models import JobPosting, TailoredArtifacts
from .cover_letter import CoverLetterGenerator
from .evaluator_panel import EvaluatorPanel
from .fact_guard import FactGuard
from .graph_retriever import GraphRetriever
from .models import ResumeData
from .outreach_drafter import OutreachDrafter
from .pdf_renderer import PdfRenderer, parse_resume_markdown
from .qa_generator import QAGenerator
from .surgical_optimizer import SurgicalOptimizer

logger = logging.getLogger(__name__)

from src.core.constants import COMMON_TECH_KEYWORDS


def extract_keywords_from_text(text: str) -> List[str]:
    """Extract known technical skills and ATS keywords from job text.

    Uses (?<!\\w)..(?!\\w) instead of \\b..\\b to handle tech terms ending in
    non-word chars like C#, T-SQL, .NET.
    """
    if not text:
        return []
    found = []
    text_lower = text.lower()
    for kw in COMMON_TECH_KEYWORDS:
        pat = re.compile(rf"(?<!\w){re.escape(kw.lower())}(?!\w)")
        if pat.search(text_lower):
            found.append(kw)
    return found


class ResumeGenerator:
    """Full-cycle Stage 3 resume tailoring and multi-artifact generation engine."""

    def __init__(
        self,
        llm: Optional[LLMGateway] = None,
        retriever: Optional[GraphRetriever] = None,
        optimizer: Optional[SurgicalOptimizer] = None,
        fact_guard: Optional[FactGuard] = None,
        evaluator_panel: Optional[EvaluatorPanel] = None,
        core_memory: Optional[CoreMemoryManager] = None,
        pdf_renderer: Optional[PdfRenderer] = None,
        cover_generator: Optional[CoverLetterGenerator] = None,
        qa_generator: Optional[QAGenerator] = None,
        outreach_drafter: Optional[OutreachDrafter] = None,
        artifacts_dir: Optional[str] = None,
    ) -> None:
        self._llm = llm
        self.retriever = retriever or GraphRetriever()
        self.optimizer = optimizer or SurgicalOptimizer(
            bold_cap=0.15, max_bold_phrases=2,
            allow_jd_tech_bold=True, allow_anchor_bold=False,
        )
        self.fact_guard = fact_guard or FactGuard()
        self.evaluator_panel = evaluator_panel or EvaluatorPanel()
        self.core_memory = core_memory or CoreMemoryManager(sync_db=False)
        self.pdf_renderer = pdf_renderer or PdfRenderer()
        self.cover_generator = cover_generator or CoverLetterGenerator(retriever=self.retriever)
        self.qa_generator = qa_generator or QAGenerator(llm=llm)
        self.outreach_drafter = outreach_drafter or OutreachDrafter()
        
        settings = get_settings()
        self.artifacts_dir = Path(artifacts_dir or settings.artifacts_dir)

    @property
    def llm(self) -> LLMGateway:
        if self._llm is None:
            self._llm = get_gateway()
        return self._llm

    def _get_job_output_dir(self, job: JobPosting) -> Path:
        """Create and return a dedicated artifacts directory for a specific job."""
        safe_company = re.sub(r"[^A-Za-z0-9_-]", "_", (job.company or "Company").strip())
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", (job.id or "job").strip())
        job_dir = self.artifacts_dir / f"{safe_company}_{safe_id}"
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def generate_raw(self, job: JobPosting) -> str:
        """Generate tailored markdown text for the given job posting."""
        jd_text = job.description or ""
        keywords = extract_keywords_from_text(f"{job.title} {jd_text}")
        if not keywords:
            keywords = ["AWS", ".NET", "C#", "Microservices", "Kafka"]

        master_content = self.retriever.get_master_content()
        if not master_content:
            from src.core.config import get_settings
            from src.core.persona import SAMPLE_FULL_NAME
            master_md_file = get_settings().master_resume_md_path
            if master_md_file.exists():
                master_content = master_md_file.read_text(encoding="utf-8")
            else:
                master_content = f"# {SAMPLE_FULL_NAME}\n**Title:** Senior Software Engineer\n\n## SUMMARY\nSenior Software Engineer with 6+ years experience.\n"

        parsed: ResumeData = parse_resume_markdown(master_content)

        # Optimize bullets with surgical bolding
        for job_entry in parsed.jobs:
            job_entry.bullets = self.optimizer.optimize_bullets(job_entry.bullets, keywords)

        # Format markdown representation
        contact_parts = [
            p for p in [
                parsed.contact_location,
                parsed.contact_phone,
                parsed.contact_email,
                parsed.contact_linkedin,
                parsed.contact_github,
                parsed.contact_portfolio,
            ] if p
        ]
        contact_line = " | ".join(contact_parts)
        lines = [
            f"# {parsed.name}",
            f"**Contact:** {contact_line}",
            "",
            "## SUMMARY",
            parsed.summary,
            "",
            "## EXPERIENCE",
        ]
        for job_entry in parsed.jobs:
            heading_parts = [p for p in [job_entry.title, job_entry.company, job_entry.location, job_entry.dates] if p]
            clean_heading = " | ".join(heading_parts) or job_entry.heading
            lines.append(f"### {clean_heading}")
            for b in job_entry.bullets:
                lines.append(f"- {b}")
            lines.append("")

        if parsed.skills:
            lines.append("## SKILLS")
            for sk in parsed.skills:
                lines.append(f"- {sk}")
            lines.append("")

        if parsed.certifications:
            lines.append("## CERTIFICATIONS")
            for cert in parsed.certifications:
                lines.append(f"- {cert}")
            lines.append("")

        if parsed.education:
            lines.append("## EDUCATION")
            for edu in parsed.education:
                lines.append(f"- {edu}")

        return "\n".join(lines)

    def generate(self, job: JobPosting, target_pages: Optional[int] = None) -> TailoredArtifacts:
        """Run full tailoring pipeline and generate all artifacts for the target job."""
        settings = get_settings()
        pages = target_pages if target_pages is not None else settings.resume_target_pages
        out_dir = self._get_job_output_dir(job)
        jd_text = job.description or ""
        keywords = extract_keywords_from_text(f"{job.title} {jd_text}")

        # 1. Retrieve GraphRAG context, causal paths & verified evidence
        evidence = self.retriever.retrieve_evidence(keywords, target_company=job.company, max_evidence=5)
        causal_paths = self.retriever.retrieve_causal_paths(keywords, max_paths=3)
        causal_evidence_lines = [f"- {cp['reasoning_chain']}" for cp in causal_paths] if causal_paths else [f"- {e}" for e in evidence]

        # 2. Parse master resume
        master_content = self.retriever.get_master_content()
        parsed: ResumeData = parse_resume_markdown(master_content) if master_content else ResumeData(name="Alex Rivera")

        # 3. Scoped MemGPT System RAM Directives
        system_ram = self.core_memory.render_system_ram()

        # 4. LLM Multi-Role Tailoring with Single-Pass Evaluator Check
        try:
            prompt = (
                f"{system_ram}\n\n"
                f"Target Company: {job.company}\n"
                f"Target Title: {job.title}\n"
                f"Job Description: {jd_text[:1000]}\n"
                f"Top Matching Keywords: {', '.join(keywords)}\n"
                f"GraphRAG Verified Causal Evidence:\n" + "\n".join(causal_evidence_lines) + "\n\n"
                f"Please produce a tailored 3-sentence summary and refined bullets across recent roles for Alex Rivera. "
                f"Respond in JSON format: {{\"summary\": \"...\", \"optimized_bullets\": [\"...\"], \"role_2_bullets\": [\"...\"]}}"
            )
            res = self.llm.generate(prompt=prompt, json_mode=True, temperature=0.2)
            parsed_json = json.loads(res)
            if "summary" in parsed_json and parsed_json["summary"]:
                is_valid, _ = self.fact_guard.validate_bullet(parsed_json["summary"])
                if is_valid:
                    parsed.summary = parsed_json["summary"]


            # Role 1 bullet tailoring
            if "optimized_bullets" in parsed_json and isinstance(parsed_json["optimized_bullets"], list):
                for i, bullet in enumerate(parsed_json["optimized_bullets"]):
                    is_valid, _ = self.fact_guard.validate_bullet(bullet)
                    if is_valid and parsed.jobs and len(parsed.jobs[0].bullets) > i:
                        parsed.jobs[0].bullets[i] = bullet

            # Role 2 bullet tailoring (multi-role experience)
            if "role_2_bullets" in parsed_json and isinstance(parsed_json["role_2_bullets"], list):
                for i, bullet in enumerate(parsed_json["role_2_bullets"]):
                    is_valid, _ = self.fact_guard.validate_bullet(bullet)
                    if is_valid and len(parsed.jobs) > 1 and len(parsed.jobs[1].bullets) > i:
                        parsed.jobs[1].bullets[i] = bullet

            # Single-pass 3-persona evaluator check
            all_top_bullets = []
            for j in parsed.jobs[:2]:
                all_top_bullets.extend(j.bullets[:2])
            eval_score = self.evaluator_panel.evaluate_draft(all_top_bullets, target_keywords=keywords)
            logger.info("Tailored resume evaluation composite score: %s/100 (Passed: %s)", eval_score.get("composite_score"), eval_score.get("passed"))
        except Exception as exc:
            logger.info("Proceeding with rule-based resume tailoring: %s", exc)

        # 4. Surgical bolding
        for job_entry in parsed.jobs:
            job_entry.bullets = self.optimizer.optimize_bullets(job_entry.bullets, keywords)

        # Clean up any legacy company-suffixed PDF artifacts in the folder
        for legacy_pdf in out_dir.glob("*.pdf"):
            if legacy_pdf.name not in ("Alex_Rivera_Resume.pdf", "Cover_Letter.pdf"):
                try:
                    legacy_pdf.unlink(missing_ok=True)
                except Exception:
                    pass

        # 5. Render ATS PDF Resume (Standard clean filename without company suffix)
        pdf_path = out_dir / "Alex_Rivera_Resume.pdf"
        self.pdf_renderer.render_from_model(
            parsed=parsed,
            output_pdf_path=pdf_path,
            target_pages=pages,
            keywords=keywords,
        )

        # Save markdown / json representation
        raw_md_path = out_dir / "tailored_resume.md"
        raw_md_text = self.generate_raw(job)
        raw_md_path.write_text(raw_md_text, encoding="utf-8")

        # 6. Cover Letter (Markdown + PDF, standard filename)
        cl_data = self.cover_generator.generate(
            company=job.company,
            jd_text=jd_text,
            candidate_name=parsed.name or "Alex Rivera",
            role_title=job.title or "Senior Software Engineer",
        )
        cl_pdf_path = out_dir / "Cover_Letter.pdf"
        self.cover_generator.render_pdf(cl_data, cl_pdf_path)

        # 7. Q&A Generation
        qa_answers = self.qa_generator.generate_answers(job)

        # 8. LinkedIn Outreach Note
        outreach_dm = self.outreach_drafter.draft_recruiter_dm(job)

        return TailoredArtifacts(
            job_id=job.id,
            resume_pdf_path=str(pdf_path.resolve()),
            resume_json_path=str(raw_md_path.resolve()),
            cover_letter_path=str(cl_pdf_path.resolve()),
            qa_answers=qa_answers,
            linkedin_outreach=outreach_dm,
            tailored_at=datetime.utcnow(),
        )
