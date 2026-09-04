"""Modern Typst PDF Resume Renderer enforcing strict ATS formatting and page budgets."""

from __future__ import annotations

import logging
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from .models import JobEntry, ResumeData

logger = logging.getLogger(__name__)


def escape_typst(text: str) -> str:
    """Escape special Typst control characters while preserving bold/italic markdown."""
    if not text:
        return ""

    # Escape raw dollars (unless already escaped)
    text = re.sub(r"(?<!\\)\$", r"\$", text)
    # Escape raw hashes
    text = re.sub(r"(?<!\\)#", r"\#", text)
    # Escape raw at signs
    text = re.sub(r"(?<!\\)@", r"\@", text)

    return text.strip()


def generate_typst_markup(resume: ResumeData, target_pages: int = 1) -> str:
    """Generate structured modern Typst markup (.typ) from ResumeData.

    Args:
        resume: ResumeData instance containing candidate sections.
        target_pages: Target page budget (1 or 2).

    Returns:
        String containing full Typst document code.
    """
    margin_x = "0.45in" if target_pages == 1 else "0.50in"
    margin_y = "0.35in" if target_pages == 1 else "0.45in"
    font_size = "9.5pt" if target_pages == 1 else "10pt"

    # Contact line synthesis
    contacts = [
        resume.contact_location,
        resume.contact_email,
        resume.contact_phone,
        resume.contact_linkedin,
        resume.contact_github,
    ]
    contact_str = " | ".join(c for c in contacts if c)

    lines: List[str] = [
        f'#set page(paper: "us-letter", margin: (x: {margin_x}, top: {margin_y}, bottom: {margin_y}))',
        f'#set text(font: ("Segoe UI", "Inter", "Arial"), size: {font_size}, fill: rgb("#0f172a"))',
        '#set par(justify: false, leading: 0.52em)',
        "",
        "// Section Divider Function",
        '#let section_header(title) = {',
        '  v(4pt)',
        '  text(size: 11pt, weight: "bold", fill: rgb("#0f172a"), tracking: 0.5pt)[#upper(title)]',
        '  v(-3pt)',
        '  line(length: 100%, stroke: 0.8pt + rgb("#cbd5e1"))',
        '  v(2pt)',
        '}',
        "",
        "// Job Heading Helper",
        '#let job_entry(title, company, loc, dates) = {',
        '  grid(',
        '    columns: (1fr, auto),',
        '    [*#title* — #text(weight: "medium")[#company]],',
        '    align(right)[#text(style: "italic", size: 8.5pt, fill: rgb("#475569"))[#loc | #dates]]',
        '  )',
        '}',
        "",
        "// Document Header",
        f'#align(center)[',
        f'  #text(size: 17pt, weight: "bold", fill: rgb("#0f172a"))[{escape_typst(resume.name or "Candidate")}]',
        f'  #v(-4pt)',
        f'  #text(size: 8.5pt, fill: rgb("#475569"))[{escape_typst(contact_str)}]',
        f']',
        "",
    ]

    # Summary
    if resume.summary:
        lines.append('section_header("Professional Summary")')
        for line in resume.summary.strip().split("\n"):
            cleaned = line.strip().lstrip("*-• ").strip()
            if cleaned:
                lines.append(f"- {escape_typst(cleaned)}")
        lines.append("")

    # Experience (Jobs)
    if resume.jobs:
        lines.append('section_header("Experience")')
        for job in resume.jobs:
            title = job.title or "Software Engineer"
            company = job.company or ""
            loc = job.location or ""
            dates = job.dates or ""
            if not company and "|" in job.heading:
                parts = [p.strip() for p in job.heading.replace("**", "").split("|")]
                title = parts[0] if len(parts) > 0 else title
                company = parts[1] if len(parts) > 1 else company
                loc = parts[2] if len(parts) > 2 else loc
                dates = parts[3] if len(parts) > 3 else dates

            lines.append(f'job_entry("{escape_typst(title)}", "{escape_typst(company)}", "{escape_typst(loc)}", "{escape_typst(dates)}")')
            lines.append("#v(-2pt)")
            for b in job.bullets:
                lines.append(f"- {escape_typst(b)}")
            lines.append("#v(2pt)")
        lines.append("")

    # Projects
    if resume.projects:
        lines.append('section_header("Projects")')
        for proj in resume.projects:
            title = proj.title or "Project"
            dates = proj.dates or ""
            lines.append(f'job_entry("{escape_typst(title)}", "", "", "{escape_typst(dates)}")')
            lines.append("#v(-2pt)")
            for b in proj.bullets:
                lines.append(f"- {escape_typst(b)}")
            lines.append("#v(2pt)")
        lines.append("")

    # Technical Skills
    if resume.skills:
        lines.append('section_header("Technical Skills")')
        for skill_item in resume.skills:
            lines.append(f"- {escape_typst(skill_item)}")
        lines.append("")

    # Education & Certifications
    if resume.education:
        lines.append('section_header("Education")')
        for edu in resume.education:
            lines.append(f"- {escape_typst(edu)}")
        lines.append("")

    if resume.certifications:
        lines.append('section_header("Certifications")')
        for cert in resume.certifications:
            lines.append(f"- {escape_typst(cert)}")
        lines.append("")

    return "\n".join(lines)



def compile_typst_to_pdf(
    resume: ResumeData,
    output_pdf_path: str,
    target_pages: int = 1
) -> str:
    """Compile ResumeData to PDF using Typst with graceful ReportLab fallback.

    Args:
        resume: ResumeData instance.
        output_pdf_path: Path where output PDF should be written.
        target_pages: Page budget (1 or 2).

    Returns:
        String path to the rendered PDF file.
    """
    output_path = Path(output_pdf_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    typst_code = generate_typst_markup(resume, target_pages=target_pages)
    typ_file_path = output_path.with_suffix(".typ")
    typ_file_path.write_text(typst_code, encoding="utf-8")

    # Check for typst CLI
    typst_bin = shutil.which("typst")
    if typst_bin:
        try:
            cmd = [typst_bin, "compile", str(typ_file_path), str(output_path)]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("Compiled Typst PDF successfully: %s", output_path)
            return str(output_path)
        except Exception as exc:
            logger.warning("Typst CLI compilation failed (%s); falling back to ReportLab.", exc)

    # Fallback to ReportLab renderer
    from .pdf_renderer import generate_resume_pdf
    return generate_resume_pdf(resume, str(output_path), target_pages=target_pages)
