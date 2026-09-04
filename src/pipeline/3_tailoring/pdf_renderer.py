"""Production-grade ReportLab PDF resume generator enforcing strict ATS formatting and page budgets.

Enforces:
- Strict 2-page max budget (or 1-page compact layout)
- KeepTogether blocks on job headers + first bullet to prevent orphan headers
- Clickable metadata links
- 0.55" / 0.45" tight margins and clean typography
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Table, TableStyle

from .models import JobEntry, ResumeData
from .pdf_styles import (
    AdaptivePageCanvas,
    PageCountCanvas,
    create_section_header_flowables,
    format_certification_split,
    format_contact_paragraph,
    format_education_split,
    format_job_heading,
    format_job_heading_split,
    get_resume_styles,
    markdown_to_reportlab_html,
    prevent_widow_words,
    sanitize_ats_markdown,
)

logger = logging.getLogger(__name__)

# Section Keys
SECTION_SUMMARY = "SUMMARY"
SECTION_EXPERIENCE = "EXPERIENCE"
SECTION_PROJECTS = "PROJECTS"
SECTION_SKILLS = "SKILLS"
SECTION_CERTIFICATIONS = "CERTIFICATIONS"
SECTION_EDUCATION = "EDUCATION"
SECTION_SKIP = "SKIP"
SECTION_SKIP_SUMMARY_VARIANTS = "SKIP_SUMMARY_VARIANTS"

# Margins
MARGIN_1PAGE_LEFT = 0.35 * inch
MARGIN_1PAGE_RIGHT = 0.45 * inch
MARGIN_1PAGE_TOP_BOTTOM = 16.0  # pt

MARGIN_2PAGE_LEFT = 0.45 * inch
MARGIN_2PAGE_RIGHT = 0.50 * inch
MARGIN_2PAGE_TOP_BOTTOM = 0.40 * inch


def clean_link_url(text: str) -> str:
    """Extract clean URL from markdown link [Text](url) or return text as is."""
    match = re.search(r"\[.*?\]\((.*?)\)", text)
    if match:
        return match.group(1).strip()
    return text.strip()


def clean_em_dashes(text: str) -> str:
    """Normalize em-dashes while preserving valid hyphens in dates."""
    return sanitize_ats_markdown(text)


def sample_mode_footer_text() -> str:
    """Return watermark / disclaimer footer when active profile is the sample persona."""
    try:
        from src.core.config import get_settings
        profile_dir = Path(get_settings().profile_dir).resolve()
        sample_dir = Path("./data/sample").resolve()
        if profile_dir == sample_dir:
            return "SAMPLE CANDIDATE — CareerGraph-AI demo"
    except Exception:
        pass
    return ""


def parse_job_heading_components(heading_str: str) -> Dict[str, str]:
    """Parse job heading line into title, company, location, dates."""
    cleaned = heading_str.replace(
        "**", "").replace("*", "").replace("📍", "").replace("🗓️", "").strip()

    if "|" in cleaned:
        parts = [p.strip() for p in cleaned.split("|") if p.strip()]
        return {
            "title": parts[0] if len(parts) > 0 else "",
            "company": parts[1] if len(parts) > 1 else "",
            "location": parts[2] if len(parts) > 2 else "",
            "dates": parts[3] if len(parts) > 3 else "",
        }

    match_dash = re.split(r"\s*[—–-]\s*", cleaned, maxsplit=1)
    if len(match_dash) == 2:
        return {
            "title": match_dash[0].strip(),
            "company": match_dash[1].strip(),
            "location": "",
            "dates": "",
        }

    return {
        "title": cleaned,
        "company": "",
        "location": "",
        "dates": "",
    }


def create_job_entry(heading: str, bullets: List[str]) -> JobEntry:
    """Helper to instantiate JobEntry with parsed component fields."""
    parsed_comp = parse_job_heading_components(heading)
    return JobEntry(
        heading=heading,
        title=parsed_comp["title"],
        company=parsed_comp["company"],
        location=parsed_comp["location"],
        dates=parsed_comp["dates"],
        bullets=bullets,
    )


def _parse_contact_line(contact_str: str, data: ResumeData) -> None:
    """Parse contact header line into structured ResumeData contact fields."""
    raw_parts = [p.strip() for p in contact_str.split("|") if p.strip()]
    for p in raw_parts:
        cleaned_p = re.sub(r"[📍📞✉️🌐💻📱📧🏠]", "", p).strip()
        if not cleaned_p:
            continue
        cleaned_p = clean_link_url(cleaned_p)
        low = cleaned_p.lower()
        if "@" in low and not data.contact_email:
            data.contact_email = cleaned_p
        elif "linkedin" in low and not data.contact_linkedin:
            data.contact_linkedin = cleaned_p
        elif "github" in low and not data.contact_github:
            data.contact_github = cleaned_p
        elif any(ext in low for ext in [".app", ".dev", ".io", ".me", "vercel", "github.io"]) and not data.contact_portfolio:
            data.contact_portfolio = cleaned_p
        elif ("http" in low or ".com" in low) and not data.contact_portfolio:
            data.contact_portfolio = cleaned_p
        elif re.search(r"^\+?[\d\s\-\(\)\.]{7,}$", cleaned_p) and not data.contact_phone:
            data.contact_phone = cleaned_p
        elif not data.contact_location:
            data.contact_location = cleaned_p


def parse_resume_markdown(content: str) -> ResumeData:
    """Unified Markdown resume parser building a structured ResumeData Pydantic model."""
    raw_lines = content.splitlines()
    data = ResumeData()

    current_sec = SECTION_SUMMARY
    current_job_header = None
    current_job_bullets: List[str] = []
    current_bullet_stories: List[str] = []
    current_story_title = ""
    current_proj_header = None
    current_proj_bullets: List[str] = []
    summary_lines: List[str] = []

    def flush_entries():
        nonlocal current_job_header, current_job_bullets, current_bullet_stories
        nonlocal current_proj_header, current_proj_bullets
        if current_job_header:
            job = create_job_entry(current_job_header, current_job_bullets)
            job.bullet_stories = current_bullet_stories[:]
            data.jobs.append(job)
            current_job_header = None
            current_job_bullets = []
            current_bullet_stories = []
        if current_proj_header:
            proj = create_job_entry(current_proj_header, current_proj_bullets)
            data.projects.append(proj)
            current_proj_header = None
            current_proj_bullets = []

    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("# "):
            header_text = line[2:].strip()
            header_text = re.sub(
                r"(?i)\s*[\.—–|-]*\s*MASTER RESUME.*$", "", header_text).strip()
            name_match = re.split(r"\s*[\.—–|-]\s*", header_text)[0].strip()
            if name_match:
                data.name = name_match
            continue

        if line.startswith("**Title:**"):
            data.title = line.replace("**Title:**", "").strip()
            continue

        if line.startswith("**Contact:**") or ((current_sec == SECTION_SUMMARY) and ("✉️" in line or "📞" in line or (line.startswith("📍") and "email" in line.lower()))):
            contact_str = line.replace("**Contact:**", "").strip()
            _parse_contact_line(contact_str, data)
            continue

        if line.startswith("## "):
            flush_entries()
            sec_upper = line[3:].strip().upper()
            if SECTION_SUMMARY in sec_upper or "PROFILES" in sec_upper:
                current_sec = SECTION_SUMMARY
            elif SECTION_EXPERIENCE in sec_upper or "BULLET" in sec_upper:
                current_sec = SECTION_EXPERIENCE
            elif "PROJECT" in sec_upper:
                current_sec = SECTION_PROJECTS
            elif "SKILL" in sec_upper:
                current_sec = SECTION_SKILLS
            elif "CERTIF" in sec_upper:
                current_sec = SECTION_CERTIFICATIONS
            elif "EDUCAT" in sec_upper:
                current_sec = SECTION_EDUCATION
            elif "GAP-FRAMING" in sec_upper:
                current_sec = SECTION_SKIP
            continue

        if current_sec in (SECTION_SKIP, SECTION_SKIP_SUMMARY_VARIANTS):
            continue

        if current_sec == SECTION_SUMMARY:
            if line.startswith("### Canonical Summary"):
                continue
            if line.startswith("### Domain-Specific"):
                current_sec = SECTION_SKIP_SUMMARY_VARIANTS
                continue
            if line.startswith(">") or line.startswith("**Work Authorization:**"):
                if line.startswith("**") and not data.name:
                    bold_name = re.findall(r"\*\*(.*?)\*\*", line)
                    if bold_name:
                        data.name = bold_name[0]
                continue
            if (line.startswith("**") or line == data.name) and (data.name.lower() in line.lower() or "master resume" in line.lower()):
                continue
            summary_lines.append(clean_em_dashes(line))

        elif current_sec == SECTION_EXPERIENCE:
            if line.startswith("### "):
                if current_job_header:
                    job = create_job_entry(
                        current_job_header, current_job_bullets)
                    job.bullet_stories = current_bullet_stories[:]
                    data.jobs.append(job)
                current_job_header = line[4:].strip()
                current_job_bullets = []
                current_bullet_stories = []
                current_story_title = ""
            elif line.startswith("📍") or line.startswith("🗓️"):
                sub_clean = line.replace(
                    "**", "").replace("*", "").replace("📍", "").replace("🗓️", "").strip()
                parts = [p.strip() for p in sub_clean.split("|") if p.strip()]
                loc_part = ""
                dates_part = ""
                for p in parts:
                    if re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4}|Present)\b", p, re.IGNORECASE):
                        dates_part = p
                    else:
                        loc_part = p
                if current_job_header:
                    comp = parse_job_heading_components(current_job_header)
                    t = comp["title"]
                    c = comp["company"]
                    l = loc_part or comp["location"]
                    d = dates_part or comp["dates"]
                    current_job_header = f"{t} | {c} | {l} | {d}"
            elif line.startswith("#### "):
                h4_text = line[5:].strip()
                story_match = re.sub(
                    r"^\*?\*?Story\s*\d+\s*[—–-]\s*", "", h4_text, flags=re.IGNORECASE).strip()
                if story_match:
                    current_story_title = story_match.rstrip("*")
            elif line.startswith("- ") or line.startswith("* "):
                current_job_bullets.append(clean_em_dashes(line[2:].strip()))
                current_bullet_stories.append(current_story_title)

        elif current_sec == SECTION_PROJECTS:
            if line.startswith("### "):
                if current_proj_header:
                    proj = create_job_entry(
                        current_proj_header, current_proj_bullets)
                    data.projects.append(proj)
                current_proj_header = line[4:].strip()
                current_proj_bullets = []
            elif line.startswith("- ") or line.startswith("* "):
                current_proj_bullets.append(clean_em_dashes(line[2:].strip()))

        elif current_sec == SECTION_SKILLS and (line.startswith("- ") or line.startswith("* ")):
            data.skills.append(clean_em_dashes(line[2:].strip()))

        elif current_sec == SECTION_CERTIFICATIONS and (line.startswith("- ") or line.startswith("* ")):
            data.certifications.append(clean_em_dashes(line[2:].strip()))

        elif current_sec == SECTION_EDUCATION and (line.startswith("- ") or line.startswith("* ")):
            data.education.append(clean_em_dashes(line[2:].strip()))

    flush_entries()

    if not data.name:
        data.name = "Alex Rivera"
    if not data.title:
        data.title = "Software Engineer"

    clean_summary = " ".join(summary_lines)
    if data.name:
        clean_summary = re.sub(
            rf"^(?:\*\*)?{re.escape(data.name)}(?:\*\*)?\s*[\.—–|-]*\s*", "", clean_summary, flags=re.IGNORECASE).strip()
    clean_summary = re.sub(r"^[\.—–|-]+\s*", "", clean_summary).strip()
    data.summary = clean_summary
    return data


def score_and_select_bullets(
    bullets: List[str],
    keywords: List[str],
    max_bullets: int,
    bullet_stories: Optional[List[str]] = None,
) -> List[str]:
    """Score and reorder bullets by keyword overlap, metrics, and action verbs."""
    if not bullets:
        return []

    metric_pattern = re.compile(
        r"(\d+%\b|\$\d+|\d+[kK]\+?|\d+[mM]\+?|sub-second|<3s|45s|99\.9\d*%)", re.IGNORECASE)

    scored = []
    for orig_idx, bullet in enumerate(bullets):
        score = 0
        bullet_upper = bullet.upper()

        for kw in keywords:
            if kw.strip() and kw.upper() in bullet_upper:
                score += 2

        if metric_pattern.search(bullet):
            score += 3

        if bullet_stories and orig_idx < len(bullet_stories) and bullet_stories[orig_idx]:
            story_upper = bullet_stories[orig_idx].upper()
            for kw in keywords:
                if kw.strip() and kw.upper() in story_upper:
                    score += 2
                    break

        scored.append((score, -orig_idx, bullet))

    scored.sort(reverse=True)
    target_count = min(len(bullets), max_bullets)
    return [t[2] for t in scored[:target_count]]


# Categories to drop entirely in 1-page mode (matched against the bold label before the colon).
_1PAGE_DROP_CATEGORIES = {"Frontend"}

# Category pairs to merge in 1-page mode: (label_A, label_B) -> merged_label.
_1PAGE_MERGE_MAP = {
    ("Generative AI & LLM Systems", "Observability, Testing & DevOps"): "AI & Observability",
}

# Max items (comma-separated skills) per category line in 1-page mode.
_1PAGE_MAX_ITEMS_PER_LINE = 10


def _extract_label_and_items(skill_line: str):
    """Parse a skill line like '**Label**: item1, item2' into (label, [items])."""
    m = re.match(r"\*\*(.+?)\*\*\s*:\s*(.*)", skill_line)
    if not m:
        return None, []
    label = m.group(1).strip()
    raw_items = m.group(2).strip()
    items = [s.strip() for s in raw_items.split(",") if s.strip()]
    return label, items


def _format_skill_line(label: str, items: List[str]) -> str:
    """Reconstruct a skills line from label + items."""
    return f"**{label}**: {', '.join(items)}"


def _strip_annotations(item: str) -> str:
    """Remove parenthetical annotations like '(Single-Table Design)' to save space."""
    return re.sub(r"\s*\([^)]*\)", "", item).strip()


def compact_skills_for_1page(skills: List[str]) -> List[str]:
    """Derive a compact 1-page skills list by dropping, merging, annotation stripping, and item capping."""
    parsed = {}
    order = []
    for line in skills:
        label, items = _extract_label_and_items(line)
        if label is None:
            order.append(line)
            continue
        parsed[label] = items
        order.append(label)

    # 1. Drop categories
    for drop in _1PAGE_DROP_CATEGORIES:
        if drop in parsed:
            del parsed[drop]
            order = [o for o in order if o != drop]

    # 2. Merge category pairs
    for (label_a, label_b), merged_label in _1PAGE_MERGE_MAP.items():
        if label_a in parsed and label_b in parsed:
            merged_items = parsed.pop(label_a) + parsed.pop(label_b)
            parsed[merged_label] = merged_items
            replaced = False
            new_order = []
            for o in order:
                if o == label_a and not replaced:
                    new_order.append(merged_label)
                    replaced = True
                elif o == label_b:
                    continue
                else:
                    new_order.append(o)
            order = new_order

    # 3 & 4. Strip annotations and cap items, then reconstruct
    result = []
    for entry in order:
        if entry in parsed:
            items = [_strip_annotations(it) for it in parsed[entry]]
            seen = set()
            deduped = []
            for it in items:
                if it not in seen:
                    seen.add(it)
                    deduped.append(it)
            capped = deduped[:_1PAGE_MAX_ITEMS_PER_LINE]
            result.append(_format_skill_line(entry, capped))
        else:
            result.append(entry)

    return result


def budget_resume_for_pages(
    data: ResumeData,
    target_pages: int = 1,
    keywords: Optional[List[str]] = None,
) -> ResumeData:
    """Transform and curate a ResumeData model to strictly fit target_pages constraint."""
    budgeted = copy.deepcopy(data)
    kws = keywords or []

    if target_pages == 1:
        role_bullet_limits = [10, 4, 1, 1]
        budgeted_jobs: List[JobEntry] = []
        for idx, job in enumerate(budgeted.jobs):
            max_b = role_bullet_limits[idx] if idx < len(
                role_bullet_limits) else 1
            curated = score_and_select_bullets(
                job.bullets, kws, max_b, job.bullet_stories)
            job_copy = job.model_copy(update={"bullets": curated})
            budgeted_jobs.append(job_copy)

        budgeted.jobs = budgeted_jobs

        budgeted_projects: List[JobEntry] = []
        for idx, proj in enumerate(budgeted.projects):
            if idx >= 1:
                break
            curated = score_and_select_bullets(
                proj.bullets, kws, 1, proj.bullet_stories)
            budgeted_projects.append(
                proj.model_copy(update={"bullets": curated}))
        budgeted.projects = budgeted_projects

        if len(budgeted.certifications) > 2:
            budgeted.certifications = budgeted.certifications[:2]
        budgeted.summary = ""
        budgeted.skills = compact_skills_for_1page(budgeted.skills)

    else:
        role_bullet_limits = [15, 5, 2, 2]
        budgeted_jobs: List[JobEntry] = []
        for idx, job in enumerate(budgeted.jobs):
            max_b = role_bullet_limits[idx] if idx < len(
                role_bullet_limits) else 2
            curated = score_and_select_bullets(
                job.bullets, kws, max_b, job.bullet_stories)
            budgeted_jobs.append(job_copy) if False else budgeted_jobs.append(job.model_copy(update={"bullets": curated}))
        budgeted.jobs = budgeted_jobs

        budgeted_projects: List[JobEntry] = []
        for proj in budgeted.projects:
            curated = score_and_select_bullets(
                proj.bullets, kws, 3, proj.bullet_stories)
            budgeted_projects.append(
                proj.model_copy(update={"bullets": curated}))
        budgeted.projects = budgeted_projects

    return budgeted


# Flowable Story Builders
def _build_header_story(parsed: ResumeData, styles: dict) -> List[Any]:
    story = [Paragraph(parsed.name, styles["name"])]
    contact_html = format_contact_paragraph(parsed)
    if contact_html:
        story.append(Paragraph(contact_html, styles["contact"]))
    return story


def _build_summary_story(parsed: ResumeData, styles: dict) -> List[Any]:
    if not parsed.summary:
        return []
    story = create_section_header_flowables(
        SECTION_SUMMARY, styles["sec_header"])
    story.append(Paragraph(markdown_to_reportlab_html(
        parsed.summary), styles["summary"]))
    return story


def _build_skills_story(parsed: ResumeData, styles: dict) -> List[Any]:
    if not parsed.skills:
        return []
    story = create_section_header_flowables(
        SECTION_SKILLS, styles["sec_header"])
    for skill_cat in parsed.skills:
        skill_html = markdown_to_reportlab_html(skill_cat)
        story.append(Paragraph(f"&bull; {skill_html}", styles["skill"]))
    return story


def _build_job_heading_flowable(
    job: JobEntry,
    styles: dict,
    is_first: bool = False,
    space_before: float = 6.0,
    col_widths: Optional[List[float]] = None,
) -> Any:
    left_html, right_html = format_job_heading_split(job)
    if not right_html:
        p_style = ParagraphStyle(
            "JobHeadSingle",
            parent=styles["job_heading"],
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=0 if is_first else space_before,
        )
        return Paragraph(format_job_heading(job), p_style)

    left_p = Paragraph(left_html, styles["job_heading_left"])
    right_p = Paragraph(right_html, styles["job_heading_right"])

    widths = col_widths or [385, 155]
    table = Table([[left_p, right_p]], colWidths=widths, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    table.spaceBefore = 0 if is_first else space_before
    table.spaceAfter = styles["job_heading"].spaceAfter
    return table


def _build_experience_story(parsed: ResumeData, styles: dict, space_before: float = 6.0, printable_width: float = 540.0) -> List[Any]:
    if not parsed.jobs:
        return []
    story = create_section_header_flowables(
        SECTION_EXPERIENCE, styles["sec_header"])
    right_w = 175.0
    left_w = printable_width - right_w
    for idx, job in enumerate(parsed.jobs):
        is_first = (idx == 0)
        heading_flowable = _build_job_heading_flowable(
            job, styles, is_first=is_first, space_before=space_before, col_widths=[left_w, right_w])
        if job.bullets:
            first_b = Paragraph(
                f"&bull; {markdown_to_reportlab_html(job.bullets[0], prevent_widows=True)}", styles["bullet"])
            story.append(KeepTogether([heading_flowable, first_b]))
            for bullet in job.bullets[1:]:
                story.append(
                    Paragraph(f"&bull; {markdown_to_reportlab_html(bullet, prevent_widows=True)}", styles["bullet"]))
        else:
            story.append(heading_flowable)
    return story


def _build_projects_story(parsed: ResumeData, styles: dict, space_before: float = 6.0, printable_width: float = 540.0) -> List[Any]:
    if not parsed.projects:
        return []
    story = create_section_header_flowables(
        SECTION_PROJECTS, styles["sec_header"])
    right_w = 80.0
    left_w = printable_width - right_w
    for idx, proj in enumerate(parsed.projects):
        is_first = (idx == 0)
        heading_flowable = _build_job_heading_flowable(
            proj, styles, is_first=is_first, space_before=space_before, col_widths=[left_w, right_w])
        if proj.bullets:
            first_b = Paragraph(
                f"&bull; {markdown_to_reportlab_html(proj.bullets[0], prevent_widows=True)}", styles["bullet"])
            story.append(KeepTogether([heading_flowable, first_b]))
            for bullet in proj.bullets[1:]:
                story.append(
                    Paragraph(f"&bull; {markdown_to_reportlab_html(bullet, prevent_widows=True)}", styles["bullet"]))
        else:
            story.append(heading_flowable)
    return story


def _build_certifications_story(parsed: ResumeData, styles: dict, printable_width: float = 540.0) -> List[Any]:
    if not parsed.certifications:
        return []
    story = create_section_header_flowables(
        SECTION_CERTIFICATIONS, styles["sec_header"])
    right_w = 175.0
    left_w = printable_width - right_w
    for idx, cert in enumerate(parsed.certifications):
        left_html, right_html = format_certification_split(cert)
        if not right_html:
            story.append(
                Paragraph(markdown_to_reportlab_html(cert), styles["cert"]))
        else:
            left_p = Paragraph(left_html, styles.get("edu_cert_left", styles["job_heading_left"]))
            right_p = Paragraph(right_html, styles.get("edu_cert_right", styles["job_heading_right"]))
            table = Table([[left_p, right_p]], colWidths=[
                          left_w, right_w], hAlign='LEFT')
            table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            table.spaceBefore = 0 if idx == 0 else 2.0
            table.spaceAfter = styles["cert"].spaceAfter
            story.append(table)
    return story


def _build_education_story(parsed: ResumeData, styles: dict, printable_width: float = 540.0) -> List[Any]:
    if not parsed.education:
        return []
    story = create_section_header_flowables(
        SECTION_EDUCATION, styles["sec_header"])
    right_w = 175.0
    left_w = printable_width - right_w
    for idx, edu in enumerate(parsed.education):
        left_html, right_html = format_education_split(edu)
        if not right_html:
            story.append(
                Paragraph(markdown_to_reportlab_html(edu), styles["edu"]))
        else:
            left_p = Paragraph(left_html, styles.get("edu_cert_left", styles["job_heading_left"]))
            right_p = Paragraph(right_html, styles.get("edu_cert_right", styles["job_heading_right"]))
            table = Table([[left_p, right_p]], colWidths=[
                          left_w, right_w], hAlign='LEFT')
            table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            table.spaceBefore = 0 if idx == 0 else 2.5
            table.spaceAfter = styles["edu"].spaceAfter
            story.append(table)
    return story


class PdfRenderer:
    """Production-grade ReportLab PDF renderer with 2-page hard limit and adaptive budgeting."""

    def __init__(self) -> None:
        pass

    def render_from_model(
        self,
        parsed: ResumeData,
        output_pdf_path: Union[Path, str],
        target_pages: int = 1,
        keywords: Optional[List[str]] = None,
    ) -> Path:
        """Render PDF document directly from ResumeData Pydantic model."""
        out_path = Path(output_pdf_path)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            import tempfile
            out_path = Path(tempfile.gettempdir()) / "output" / out_path.name
            out_path.parent.mkdir(parents=True, exist_ok=True)

        budgeted = budget_resume_for_pages(
            parsed, target_pages=target_pages, keywords=keywords)

        temp_pdf = out_path.with_name(f"._{out_path.name}")
        def _build_with_styles(styles_dict: dict) -> int:
            if target_pages == 1:
                left_m = MARGIN_1PAGE_LEFT
                right_m = MARGIN_1PAGE_RIGHT
                tb_m = MARGIN_1PAGE_TOP_BOTTOM
            else:
                left_m = MARGIN_2PAGE_LEFT
                right_m = MARGIN_2PAGE_RIGHT
                tb_m = MARGIN_2PAGE_TOP_BOTTOM

            printable_w = 612.0 - left_m - right_m

            doc = SimpleDocTemplate(
                str(temp_pdf),
                pagesize=letter,
                leftMargin=left_m,
                rightMargin=right_m,
                topMargin=tb_m,
                bottomMargin=tb_m,
            )
            story = []
            story.extend(_build_header_story(budgeted, styles_dict))
            story.extend(_build_summary_story(budgeted, styles_dict))
            story.extend(_build_skills_story(budgeted, styles_dict))
            space_before = 3.5 if target_pages == 1 else 7.5
            story.extend(_build_experience_story(
                budgeted, styles_dict, space_before=space_before, printable_width=printable_w))
            story.extend(_build_projects_story(budgeted, styles_dict,
                         space_before=space_before, printable_width=printable_w))
            story.extend(_build_certifications_story(
                budgeted, styles_dict, printable_width=printable_w))
            story.extend(_build_education_story(
                budgeted, styles_dict, printable_width=printable_w))

            footer_txt = sample_mode_footer_text()
            if footer_txt:
                story.append(Paragraph(footer_txt, styles_dict["contact"]))

            AdaptivePageCanvas.last_page_count = 0
            doc.build(story, canvasmaker=AdaptivePageCanvas)
            return AdaptivePageCanvas.last_page_count

        if target_pages == 1:
            compact_styles = get_resume_styles(compact=True)
            pages = _build_with_styles(compact_styles)
            if pages > 1:
                ultra_styles = get_resume_styles(ultra_compact=True)
                pages = _build_with_styles(ultra_styles)
                # Adaptive progressive bullet trimmer to guarantee strict 1-page fit
                while pages > 1 and any(len(j.bullets) > 1 for j in budgeted.jobs):
                    longest_job = max(budgeted.jobs, key=lambda j: len(j.bullets))
                    if len(longest_job.bullets) <= 1:
                        break
                    longest_job.bullets = longest_job.bullets[:-1]
                    pages = _build_with_styles(ultra_styles)
        else:
            styles = get_resume_styles()
            pages = _build_with_styles(styles)
            if pages > 2:
                compact_styles = get_resume_styles(compact=True)
                pages = _build_with_styles(compact_styles)
                if pages > 2:
                    ultra_styles = get_resume_styles(ultra_compact=True)
                    pages = _build_with_styles(ultra_styles)
                    # Adaptive progressive bullet trimmer to guarantee strict 2-page fit
                    while pages > 2 and any(len(j.bullets) > 1 for j in budgeted.jobs):
                        longest_job = max(budgeted.jobs, key=lambda j: len(j.bullets))
                        if len(longest_job.bullets) <= 1:
                            break
                        longest_job.bullets = longest_job.bullets[:-1]
                        pages = _build_with_styles(ultra_styles)

        try:
            if out_path.exists():
                out_path.unlink()
            temp_pdf.replace(out_path)
            return out_path
        except (PermissionError, OSError):
            return temp_pdf

    def render(
        self,
        resume_source: Union[Path, str, ResumeData],
        output_pdf_path: Union[Path, str],
        target_pages: int = 1,
        keywords: Optional[List[str]] = None,
    ) -> Path:
        """Render resume from markdown string, Path, or ResumeData model."""
        if isinstance(resume_source, ResumeData):
            return self.render_from_model(resume_source, output_pdf_path, target_pages=target_pages, keywords=keywords)

        if isinstance(resume_source, Path) or (isinstance(resume_source, str) and "\n" not in resume_source and Path(resume_source).exists()):
            p = Path(resume_source)
            if not p.exists():
                raise FileNotFoundError(f"Resume source file not found: {p}")
            content = p.read_text(encoding="utf-8")
        else:
            content = str(resume_source)

        parsed = parse_resume_markdown(content)
        return self.render_from_model(parsed, output_pdf_path, target_pages=target_pages, keywords=keywords)


def render_pdf_resume(
    raw_resume_source: Union[Path, str],
    output_pdf_path: Union[Path, str],
    parsed_data: Optional[ResumeData] = None,
    target_pages: int = 1,
    keywords: Optional[List[str]] = None,
) -> Path:
    """Functional convenience wrapper for PdfRenderer."""
    renderer = PdfRenderer()
    if parsed_data is not None:
        return renderer.render_from_model(parsed_data, output_pdf_path, target_pages=target_pages, keywords=keywords)
    return renderer.render(raw_resume_source, output_pdf_path, target_pages=target_pages, keywords=keywords)


def generate_resume_pdf(
    resume_data: ResumeData,
    output_pdf_path: Union[Path, str],
    target_pages: int = 1,
    keywords: Optional[List[str]] = None,
) -> str:
    """Generate ATS PDF resume from ResumeData model via ReportLab."""
    res_path = render_pdf_resume(
        raw_resume_source="",
        output_pdf_path=output_pdf_path,
        parsed_data=resume_data,
        target_pages=target_pages,
        keywords=keywords,
    )
    return str(res_path)


def compile_resume_pdf(
    resume_data: ResumeData,
    output_pdf_path: Union[Path, str],
    backend: str = "reportlab",
    target_pages: int = 1,
    keywords: Optional[List[str]] = None,
) -> str:
    """Unified PDF compiler factory dispatching to ReportLab or Typst."""
    if backend.lower() == "typst":
        from .typst_renderer import compile_typst_to_pdf
        return compile_typst_to_pdf(resume_data, str(output_pdf_path), target_pages=target_pages)
    else:
        return generate_resume_pdf(resume_data, output_pdf_path, target_pages=target_pages, keywords=keywords)

