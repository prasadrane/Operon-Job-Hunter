"""ReportLab styling, color palettes, ParagraphStyles, and HTML formatting helpers for PDF rendering."""

from __future__ import annotations

import re
from xml.sax.saxutils import escape
from typing import Dict, List, Tuple
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Paragraph

from .models import JobEntry, ResumeData

MAX_PAGES = 2

# Professional Color Palette
COLOR_DARK = colors.HexColor("#1a1a2e")      # Name, Section Headers
COLOR_ACCENT = colors.HexColor("#0f3460")    # Job Titles, Clickable Links
COLOR_BODY = colors.HexColor("#374151")      # Bullets, Skills, Education
COLOR_META = colors.HexColor("#6b7280")      # Contact Line, Location, Dates
COLOR_RULE = colors.HexColor("#d1d5db")      # Horizontal Rule Line


class PageCountCanvas(canvas.Canvas):
    """Canvas recorder to monitor and enforce page constraints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._page_count = 0

    def showPage(self):
        self._page_count += 1
        super().showPage()

    def save(self):
        if self._page_count > MAX_PAGES:
            pass
        super().save()


class AdaptivePageCanvas(PageCountCanvas):
    """Canvas that records total generated pages for adaptive multi-pass compaction."""

    last_page_count = 0

    def showPage(self):
        super().showPage()
        AdaptivePageCanvas.last_page_count = self._page_count


def get_resume_styles(compact: bool = False, ultra_compact: bool = False) -> Dict[str, ParagraphStyle]:
    """Return configured ReportLab ParagraphStyles for ATS resume layout with adaptive compact modes."""
    styles = getSampleStyleSheet()
    font_family = "Helvetica"
    font_bold = "Helvetica-Bold"

    if ultra_compact:
        body_size, body_lead, bullet_space = 8.4, 10.8, 1.0
        sec_size, sec_lead, sec_space = 9.2, 11.2, 2.0
        name_size, name_lead, name_space = 18.0, 20.5, 2.0
        contact_size, contact_lead, contact_space = 8.6, 10.8, 3.5
    elif compact:
        body_size, body_lead, bullet_space = 8.6, 11.2, 1.3
        sec_size, sec_lead, sec_space = 9.5, 11.8, 2.5
        name_size, name_lead, name_space = 18.5, 21.5, 2.5
        contact_size, contact_lead, contact_space = 8.8, 11.2, 4.0
    else:
        body_size, body_lead, bullet_space = 9.2, 12.5, 2.8
        sec_size, sec_lead, sec_space = 10.2, 12.8, 4.5
        name_size, name_lead, name_space = 21.0, 24.0, 5.0
        contact_size, contact_lead, contact_space = 9.5, 12.5, 8.0

    return {
        "name": ParagraphStyle(
            "ResName",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=name_size,
            leading=name_lead,
            textColor=COLOR_DARK,
            spaceAfter=name_space,
            alignment=0,
        ),
        "contact": ParagraphStyle(
            "ResContact",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=contact_size,
            leading=contact_lead,
            textColor=COLOR_META,
            spaceAfter=contact_space,
            alignment=0,
        ),
        "sec_header": ParagraphStyle(
            "ResSecHeader",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=sec_size,
            leading=sec_lead,
            textColor=COLOR_DARK,
            spaceAfter=sec_space,
            alignment=0,
            keepWithNext=True,
        ),
        "job_heading": ParagraphStyle(
            "ResJobHeading",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=sec_size,
            leading=sec_lead,
            textColor=COLOR_DARK,
            spaceAfter=3 if (compact or ultra_compact) else 4,
            alignment=0,
        ),
        "job_heading_left": ParagraphStyle(
            "ResJobHeadingLeft",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=sec_size,
            leading=sec_lead,
            textColor=COLOR_DARK,
            spaceAfter=0,
            alignment=0,
        ),
        "project_heading_left": ParagraphStyle(
            "ResProjectHeadingLeft",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=9.4 if not (compact or ultra_compact) else 9.0,
            leading=12.2 if not (compact or ultra_compact) else 11.8,
            textColor=COLOR_DARK,
            spaceAfter=0,
            alignment=0,
        ),
        "job_heading_right": ParagraphStyle(
            "ResJobHeadingRight",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=body_size,
            leading=sec_lead,
            textColor=COLOR_META,
            spaceAfter=0,
            alignment=2,
        ),
        "bullet": ParagraphStyle(
            "ResBullet",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=body_size,
            leading=body_lead,
            textColor=COLOR_BODY,
            leftIndent=0,
            firstLineIndent=0,
            spaceAfter=bullet_space,
            alignment=0,
        ),
        "summary": ParagraphStyle(
            "ResSummary",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=body_size,
            leading=body_lead,
            textColor=COLOR_BODY,
            spaceAfter=4 if (compact or ultra_compact) else 6,
            alignment=0,
        ),
        "skill": ParagraphStyle(
            "ResSkill",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=body_size,
            leading=body_lead -
            0.2 if not (compact or ultra_compact) else body_lead,
            textColor=COLOR_BODY,
            leftIndent=0,
            spaceAfter=2.0 if (compact or ultra_compact) else 2.2,
            alignment=0,
        ),
        "cert": ParagraphStyle(
            "ResCert",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=8.6 if not (compact or ultra_compact) else 8.3,
            leading=11.2 if not (compact or ultra_compact) else 10.8,
            textColor=COLOR_BODY,
            spaceAfter=1.5 if (compact or ultra_compact) else 2,
            alignment=0,
        ),
        "edu": ParagraphStyle(
            "ResEdu",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=8.6 if not (compact or ultra_compact) else 8.3,
            leading=11.2 if not (compact or ultra_compact) else 10.8,
            textColor=COLOR_BODY,
            spaceAfter=1.5 if (compact or ultra_compact) else 2,
            alignment=0,
        ),
        "edu_cert_left": ParagraphStyle(
            "ResEduCertLeft",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=8.6 if not (compact or ultra_compact) else 8.3,
            leading=11.2 if not (compact or ultra_compact) else 10.8,
            textColor=COLOR_DARK,
            spaceAfter=0,
            alignment=0,
        ),
        "edu_cert_right": ParagraphStyle(
            "ResEduCertRight",
            parent=styles["Normal"],
            fontName=font_family,
            fontSize=8.4 if not (compact or ultra_compact) else 8.1,
            leading=11.2 if not (compact or ultra_compact) else 10.8,
            textColor=COLOR_META,
            spaceAfter=0,
            alignment=2,
        ),
    }


def sanitize_ats_markdown(text: str) -> str:
    """Normalize raw HTML tags, date range hyphens, dashes, and whitespace in Markdown."""
    if not text:
        return ""
    # 1. Normalize raw HTML tags to Markdown delimiters
    text = re.sub(r"<\s*/?\s*(?:b|strong)\s*>", "**", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/?\s*(?:i|em)\s*>", "*", text, flags=re.IGNORECASE)
    # 2. Normalize unicode em-dashes, en-dashes, and special horizontal bars to standard ASCII hyphen
    text = re.sub(r"[\u2014\u2013\u2015\u2012\u2011\u2010—–―]", " - ", text)
    # 3. Normalize date range hyphens: 'Jan 2023 - Jul 2025' or '2018 - 2019'
    text = re.sub(
        r"(\b[A-Za-z]{3}\s+\d{4}|\b\d{4})\s*-\s*([A-Za-z]{3}\s+\d{4}|\b\d{4}|\bPresent\b)",
        r"\1 - \2",
        text,
    )
    # 4. Collapse multiple hyphens or redundant spaces around dashes
    text = re.sub(r"\s+-\s+", " - ", text)
    text = re.sub(r"\s*-\s*-\s*", " - ", text)
    # 5. Collapse multiple spaces (preserving newlines if present)
    return re.sub(r"[ \t]+", " ", text).strip()


def prevent_widow_words(html_text: str) -> str:
    """Insert a non-breaking space between the last two words to prevent single-word orphan lines."""
    if not html_text or " " not in html_text:
        return html_text
    # Avoid replacing space inside an HTML tag attribute
    return re.sub(r"\s+([^\s<]+)$", r"&nbsp;\1", html_text.rstrip())


def markdown_to_reportlab_html(text: str, prevent_widows: bool = False) -> str:
    """Convert Markdown bold/italics/backticks and links to ReportLab compatible HTML."""
    if not text:
        return ""
    sanitized = sanitize_ats_markdown(text)
    # Escape source text before adding ReportLab markup
    escaped = escape(sanitized, entities={"'": "&apos;", '"': "&quot;"})
    # Convert markdown links [text](url) -> <a href="url"><font color="#0f3460">text</font></a>
    result = re.sub(
        r"\[([^]]+)\]\(([^)]+)\)",
        r'<a href="\2"><font color="#0f3460">\1</font></a>',
        escaped,
    )
    # Convert code backticks `code` -> <b>code</b>
    result = re.sub(r"`([^`]+)`", r"<b>\1</b>", result)
    # Convert strong **bold** and __bold__ -> <b>bold</b>
    result = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<b>{m.group(1) or m.group(2)}</b>", result)
    # Convert emphasis *italic* and _italic_ -> <i>italic</i>
    result = re.sub(r"\*([^*\n]+)\*|(?<!\w)_([^_\n]+)_(?!\w)", lambda m: f"<i>{m.group(1) or m.group(2)}</i>", result)
    # Strip any stray unmatched asterisks
    result = result.replace("*", "")
    if prevent_widows:
        result = prevent_widow_words(result)
    return result.strip()


def format_job_heading_split(job: JobEntry) -> Tuple[str, str]:
    """Format job heading into (left_html, right_html) for two-column presentation."""
    left_parts = []
    if job.title and job.company:
        left_parts.append(
            f'<font color="#0f3460"><b>{job.title}</b></font> | <b>{job.company}</b>')
    elif job.title or job.company:
        left_parts.append(
            f'<font color="#0f3460"><b>{job.title or job.company}</b></font>')
    else:
        left_parts.append(job.heading or "")

    right_parts = []
    if job.location:
        right_parts.append(f'<i>{job.location}</i>')
    if job.dates:
        dates_clean = re.sub(r"\s*[—–-]\s*", " - ", job.dates).strip()
        right_parts.append(f'<i>{dates_clean}</i>')

    left_html = " | ".join(left_parts)
    right_html = f'<font color="#6b7280">{" | ".join(right_parts)}</font>' if right_parts else ""
    return left_html, right_html


def format_education_split(edu_str: str) -> Tuple[str, str]:
    """Format education item into (left_html, right_html) for two-column presentation."""
    if not edu_str:
        return "", ""

    # 1. Strip leading list bullets (- or • or * followed by whitespace)
    clean = re.sub(r"^(?:[\-•]\s*|\*\s+)", "", edu_str.strip())
    clean = sanitize_ats_markdown(clean)

    # 2. Extract parenthesized dates: (2018 - 2019) or (2009 - 2013)
    date_match = re.search(r"\(([^)]*\d{4}[^)]*)\)", clean)
    dates = ""
    if date_match:
        raw_dates = date_match.group(1).strip()
        dates = re.sub(r"\s*[—–-]\s*", " - ", raw_dates).strip()
        clean = re.sub(r"\s*\([^)]*\d{4}[^)]*\)", "", clean).strip()

    # 3. Extract optional GPA: e.g. GPA: 3.9/4.0 or **GPA:** 3.8
    gpa_match = re.search(
        r"(?:\|\s*)?(?:GPA[:\s]+[0-9\.]+(?:/[0-9\.]+)?|\*\*GPA:\*\*\s*[0-9\.]+(?:/[0-9\.]+)?)\b",
        clean,
        flags=re.IGNORECASE,
    )
    gpa_str = ""
    if gpa_match:
        raw_gpa = gpa_match.group(0).strip(" |*")
        gpa_val_match = re.search(r"[0-9\.]+(?:/[0-9\.]+)?", raw_gpa)
        if gpa_val_match:
            gpa_str = f"GPA: {gpa_val_match.group(0)}"
        clean = clean[:gpa_match.start()] + clean[gpa_match.end():]
        clean = clean.strip(" |")

    # 4. Extract Degree: prioritize **degree** bold span, otherwise split on first separator
    deg_match = re.search(r"\*\*(.*?)\*\*", clean)
    if deg_match:
        degree = deg_match.group(1).strip(" \t\n*—–-.,")
        remainder = clean[:deg_match.start()] + clean[deg_match.end():]
    else:
        parts = re.split(r"\s*[—–|]\s*", clean, maxsplit=1)
        if len(parts) == 2:
            degree = parts[0].strip(" \t\n*—–-.,")
            remainder = parts[1]
        elif "," in clean:
            comma_parts = [p.strip(" \t\n*—–-.") for p in clean.split(",") if p.strip(" \t\n*—–-.")]
            degree = comma_parts[0]
            remainder = ", ".join(comma_parts[1:])
        else:
            degree = clean.strip(" \t\n*—–-.,")
            remainder = ""

    degree = degree.replace("*", "").strip(" \t\n—–-.,")

    # 5. Extract School and Location from remainder
    remainder = remainder.strip(" \t\n—–-.,")
    sub_parts = [p.strip(" \t\n—–-.") for p in re.split(r"[,|—–]", remainder) if p.strip(" \t\n—–-.")]
    if len(sub_parts) >= 3:
        school = sub_parts[0]
        location = f"{sub_parts[1]}, {sub_parts[2]}"
    elif len(sub_parts) == 2:
        school = sub_parts[0]
        location = sub_parts[1]
    elif len(sub_parts) == 1:
        school = sub_parts[0]
        location = ""
    else:
        school = ""
        location = ""

    left_parts = []
    if degree:
        left_parts.append(f'<font color="#0f3460"><b>{degree}</b></font>')
    if school:
        left_parts.append(markdown_to_reportlab_html(school))
    if gpa_str:
        left_parts.append(f'<font color="#374151"><b>{gpa_str}</b></font>')

    left_html = " | ".join(left_parts) if left_parts else markdown_to_reportlab_html(edu_str)

    right_parts = []
    if location:
        right_parts.append(location)
    if dates:
        right_parts.append(dates)

    right_html = f'<font color="#6b7280"><i>{" | ".join(right_parts)}</i></font>' if right_parts else ""
    return left_html, right_html


def format_certification_split(cert_str: str) -> Tuple[str, str]:
    """Format certification item into (left_html, right_html) for two-column presentation."""
    if not cert_str:
        return "", ""

    # Strip leading list bullets (- or • or * followed by whitespace)
    clean = re.sub(r"^(?:[\-•]\s*|\*\s+)", "", cert_str.strip())
    clean = sanitize_ats_markdown(clean)

    # 1. Extract dates / metadata in parentheses: e.g. *(Issued: Apr 2026 | Expires: Apr 2029)*
    date_match = re.search(r"\*?\s*\((Issued:[^)]*|Expires:[^)]*|Issued\s+[^)]*|\d{4}[^)]*)\)\s*\*?", clean, flags=re.IGNORECASE)
    dates_str = ""
    if date_match:
        dates_str = date_match.group(1).strip(" *()")
        clean = clean[:date_match.start()] + clean[date_match.end():]
        clean = clean.strip(" \t\n*—–-.,")

    # 2. Extract certification name (with optional link [Name](url)) and issuer
    # Check if there is an explicit separator between cert name and issuer
    sep_match = re.search(r"\s*(?:—|–| - | \| |\.\s+)\s*", clean)
    if sep_match:
        cert_part = clean[:sep_match.start()].strip(" \t\n*—–-.,")
        issuer_part = clean[sep_match.end():].strip(" \t\n*—–-.,")
    else:
        cert_part = clean.strip(" \t\n*—–-.,")
        issuer_part = ""

    left_parts = []
    if cert_part:
        left_parts.append(f'<font color="#0f3460"><b>{markdown_to_reportlab_html(cert_part)}</b></font>')
    if issuer_part:
        left_parts.append(markdown_to_reportlab_html(issuer_part))

    left_html = " | ".join(left_parts) if left_parts else markdown_to_reportlab_html(cert_str)
    right_html = f'<font color="#6b7280"><i>{dates_str}</i></font>' if dates_str else ""
    return left_html, right_html


def format_job_heading(job: JobEntry) -> str:
    """Format single line Job Heading: Job Title | Company Name | Location | Dates."""
    heading_parts = []
    if job.title and job.company:
        heading_parts.append(
            f'<font color="#0f3460"><b>{job.title}</b> | <b>{job.company}</b></font>')
    elif job.title or job.company:
        heading_parts.append(
            f'<font color="#0f3460"><b>{job.title or job.company}</b></font>')

    meta_parts = []
    if job.location:
        meta_parts.append(f'<i>{job.location}</i>')
    if job.dates:
        dates_clean = job.dates.replace("–", " - ").replace("—", " - ")
        meta_parts.append(f'<i>{dates_clean}</i>')

    if meta_parts:
        heading_parts.append(
            f'<font color="#6b7280">{" | ".join(meta_parts)}</font>')

    return " | ".join(heading_parts) if heading_parts else job.heading


def format_contact_paragraph(data: ResumeData) -> str:
    """Format contact items into reportlab clickable HTML paragraph string dynamically."""
    items = []
    if data.contact_location:
        items.append(data.contact_location)
    if data.contact_phone:
        items.append(data.contact_phone)
    if data.contact_email:
        email_clean = data.contact_email.replace("mailto:", "")
        items.append(
            f'<a href="mailto:{email_clean}"><font color="#0f3460">{email_clean}</font></a>')
    if data.contact_linkedin:
        link_url = data.contact_linkedin if data.contact_linkedin.startswith(
            "http") else f"https://{data.contact_linkedin}"
        display_text = data.contact_linkedin.replace(
            "https://", "").replace("http://", "").replace("www.", "")
        if data.contact_github and "linkedin.com/in/" in display_text:
            display_text = display_text.replace("linkedin.com/in/", "in/")
        items.append(
            f'<a href="{link_url}"><font color="#0f3460">{display_text}</font></a>')
    if data.contact_github:
        gh_url = data.contact_github if data.contact_github.startswith(
            "http") else f"https://{data.contact_github}"
        display_gh = data.contact_github.replace(
            "https://", "").replace("http://", "").replace("www.", "")
        items.append(
            f'<a href="{gh_url}"><font color="#0f3460">{display_gh}</font></a>')
    if data.contact_portfolio:
        port_url = data.contact_portfolio if data.contact_portfolio.startswith(
            "http") else f"https://{data.contact_portfolio}"
        display_text = data.contact_portfolio.replace(
            "https://", "").replace("http://", "").replace("www.", "")
        items.append(
            f'<a href="{port_url}"><font color="#0f3460">{display_text}</font></a>')

    return " | ".join(items)


def create_section_header_flowables(title: str, sec_style: ParagraphStyle) -> list:
    """Create divider line and section header flowables."""
    return [
        HRFlowable(width="100%", thickness=0.5, color=COLOR_RULE,
                   spaceBefore=6, spaceAfter=6),
        Paragraph(title, sec_style),
    ]
