"""FAANG Gold-Standard tailored cover letter generator producing Markdown and 1-page ReportLab PDF."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from typing import List, Optional, Union

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from src.core.persona import SAMPLE_CONTACT_LINE, SAMPLE_FULL_NAME

logger = logging.getLogger(__name__)


@dataclass
class CoverLetterData:
    """Structured FAANG gold-standard cover letter container."""

    candidate_name: str = SAMPLE_FULL_NAME
    contact_line: str = SAMPLE_CONTACT_LINE
    company_name: str = "Target Company"
    role_title: str = "Senior Software Engineer"
    salutation: str = ""
    opening_hook: str = ""
    proof_points: List[str] = field(default_factory=list)
    alignment_closing: str = ""
    paragraphs: List[str] = field(default_factory=list)
    sign_off: str = f"Sincerely,\n{SAMPLE_FULL_NAME}"


class CoverLetterGenerator:
    """Generates FAANG/Tier-1 executive cover letters grounded in candidate metrics and JD themes."""

    PROOF_LIBRARY = [
        {
            "category": "Cloud & Kafka",
            "keywords": ["kafka", "msk", "event", "streaming", "aws", "ecs", "cloud", "distributed", "scale"],
            "title": "Cloud Modernization & Event-Driven Governance",
            "bullet": "Led the cloud modernization of mission-critical services to <b>AWS ECS Fargate</b> (achieving 99.95% uptime, 40% cost reduction) and established enterprise-wide <b>Kafka/AWS MSK</b> governance standards adopted across 5 engineering teams within 3 months.",
        },
        {
            "category": "Performance & Observability",
            "keywords": ["performance", "latency", "observability", "dynatrace", "splunk", "profiling", "windbg", "tuning", "concurrency", "reliability"],
            "title": "Observability & Low-Latency Performance",
            "bullet": "Re-engineered <b>Dynatrace</b> synthetic monitoring to slash on-call alert noise by 80% (~20 engineering hours reclaimed monthly), and diagnosed thread-lock bottlenecks with <b>WinDbg</b> to reduce enterprise report latency from 45s to sub-3s.",
        },
        {
            "category": "Modern Architecture & AI",
            "keywords": ["ai", "llm", "bedrock", "genai", "prompt", "dynamodb", "angular", "fastapi", "microservices", "architecture"],
            "title": "AI Orchestration & Scalable Architecture",
            "bullet": "Architected an AI intent-to-API router on <b>Amazon Bedrock (Claude Sonnet)</b> cutting lookup latency by 70% with strict prompt guardrails, and designed a single-table <b>DynamoDB + Angular 18</b> platform cutting configuration deploy times from 14 days to sub-15 minutes.",
        },
    ]

    def __init__(self, retriever: Optional[Any] = None, brain: Optional[Any] = None) -> None:
        self.retriever = retriever
        self._brain = brain

    @property
    def brain(self) -> Optional[Any]:
        if self._brain is None:
            from src.brain.factory import get_brain
            self._brain = get_brain()
        return self._brain

    def generate(
        self,
        company: str,
        jd_text: str,
        candidate_name: str = "Alex Rivera",
        role_title: str = "Senior Software Engineer",
    ) -> CoverLetterData:
        """Generate a FAANG gold-standard cover letter (<220 words) with grounded proof points."""
        target_company = company.strip() if company and company.strip() else "Engineering Team"
        jd_lower = jd_text.lower() if jd_text else ""

        # 1. Opening Hook: Immediate scale and business value promise (with Career Brain avatar if available)
        opening_hook = (
            f"Having architected cloud-native and event-driven platforms that reduced infrastructure costs by 40% "
            f"and slashed on-call alert noise by 80% across mission-critical services, I am eager to bring my "
            f"background in high-throughput distributed systems and cloud modernization to {target_company}'s "
            f"{role_title} team."
        )

        # 2. Select 2-3 most relevant grounded proof points (from GraphRetriever causal paths or PROOF_LIBRARY)
        selected_points: List[str] = []
        if self.retriever and hasattr(self.retriever, "retrieve_causal_paths"):
            try:
                raw_words = re.findall(r"[A-Za-z0-9+#]+", jd_lower)
                causal = self.retriever.retrieve_causal_paths(raw_words[:10], max_paths=2)
                for cp in causal:
                    tech_title = "/".join(cp.get("tech", [])[:2]) or cp.get("story", "Architecture")
                    selected_points.append(f"<b>{tech_title}:</b> {cp.get('action', '')}")
            except Exception as e:
                logger.debug("Dynamic causal proof generation fallback: %s", e)

        if not selected_points:
            for item in self.PROOF_LIBRARY:
                score = sum(1 for kw in item["keywords"] if kw in jd_lower)
                if score > 0 or len(selected_points) < 2:
                    selected_points.append(f"<b>{item['title']}:</b> {item['bullet']}")

        # Ensure at least 2 distinct proof points
        if len(selected_points) < 2:
            selected_points = [
                f"<b>{self.PROOF_LIBRARY[0]['title']}:</b> {self.PROOF_LIBRARY[0]['bullet']}",
                f"<b>{self.PROOF_LIBRARY[1]['title']}:</b> {self.PROOF_LIBRARY[1]['bullet']}",
            ]

        # 3. Alignment Closing: Strategic alignment and conversation invite
        alignment_closing = (
            f"I admire {target_company}'s high bar for engineering excellence and operational rigor. "
            f"I would welcome the opportunity to discuss how my hands-on distributed systems expertise and "
            f"pragmatic architecture leadership can contribute to your platform."
        )

        salutation = f"Dear {target_company} Engineering Team,"
        paragraphs = [opening_hook] + selected_points[:2] + [alignment_closing]

        return CoverLetterData(
            candidate_name=candidate_name,
            company_name=target_company,
            role_title=role_title,
            salutation=salutation,
            opening_hook=opening_hook,
            proof_points=selected_points[:2],
            alignment_closing=alignment_closing,
            paragraphs=paragraphs,
            sign_off=f"Sincerely,\n{candidate_name}",
        )


    def render_markdown(self, data: CoverLetterData) -> str:
        """Render FAANG cover letter as clean formatted markdown."""
        lines = [
            f"# {data.candidate_name}",
            f"{data.contact_line}\n",
            f"**Target Company:** {data.company_name} | **Role:** {data.role_title}\n",
            f"{data.salutation}\n",
            f"{data.opening_hook}\n",
            "Key technical accomplishments aligned with this role:",
        ]
        for pt in data.proof_points:
            # Clean HTML tags for markdown
            clean_pt = pt.replace("<b>", "**").replace("</b>", "**")
            lines.append(f"- {clean_pt}")

        lines.append(f"\n{data.alignment_closing}\n")
        lines.append(f"{data.sign_off}")
        return "\n".join(lines)

    def render_pdf(self, data: CoverLetterData, output_path: Union[Path, str]) -> Path:
        """Render FAANG gold-standard 1-page PDF using ReportLab with clean typography."""
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(out_path),
            pagesize=letter,
            leftMargin=0.65 * inch,
            rightMargin=0.65 * inch,
            topMargin=0.60 * inch,
            bottomMargin=0.60 * inch,
        )

        font_body = "Helvetica"
        font_bold = "Helvetica-Bold"
        color_dark = colors.HexColor("#1a1a2e")
        color_body = colors.HexColor("#374151")
        color_meta = colors.HexColor("#6b7280")
        color_rule = colors.HexColor("#d1d5db")

        style_name = ParagraphStyle(
            "CLName",
            fontName=font_bold,
            fontSize=16,
            leading=20,
            textColor=color_dark,
            alignment=TA_LEFT,
            spaceAfter=3,
        )
        style_contact = ParagraphStyle(
            "CLContact",
            fontName=font_body,
            fontSize=9,
            leading=12,
            textColor=color_meta,
            alignment=TA_LEFT,
            spaceAfter=6,
        )
        style_target = ParagraphStyle(
            "CLTarget",
            fontName=font_bold,
            fontSize=10.5,
            leading=14,
            textColor=color_dark,
            alignment=TA_LEFT,
            spaceAfter=12,
        )
        style_body = ParagraphStyle(
            "CLBody",
            fontName=font_body,
            fontSize=10,
            leading=14.5,
            textColor=color_body,
            alignment=TA_LEFT,
            spaceAfter=8,
        )
        style_bullet = ParagraphStyle(
            "CLBullet",
            fontName=font_body,
            fontSize=9.8,
            leading=14,
            textColor=color_body,
            alignment=TA_LEFT,
            leftIndent=14,
            spaceAfter=6,
        )
        style_signoff = ParagraphStyle(
            "CLSignoff",
            fontName=font_body,
            fontSize=10,
            leading=14,
            textColor=color_body,
            alignment=TA_LEFT,
            spaceBefore=10,
        )

        def _clean(t: str) -> str:
            if not t:
                return ""
            cleaned = re.sub(r"[\u2014\u2013\u2015\u2012\u2011\u2010—–―]", " - ", t)
            cleaned = re.sub(r"\s+-\s+", " - ", cleaned)
            cleaned = re.sub(r"\s*-\s*-\s*", " - ", cleaned)
            return cleaned.strip()

        story = []
        # Header block
        story.append(Paragraph(_clean(data.candidate_name), style_name))
        story.append(Paragraph(_clean(data.contact_line), style_contact))
        story.append(HRFlowable(width="100%", thickness=0.75, color=color_rule, spaceBefore=4, spaceAfter=10))

        # Salutation & Role Target
        story.append(Paragraph(f"<b>Application for {_clean(data.role_title)}</b> - {_clean(data.company_name)}", style_target))
        story.append(Paragraph(_clean(data.salutation), style_body))
        story.append(Spacer(1, 4))

        # Paragraph 1: Opening Hook
        story.append(Paragraph(_clean(data.opening_hook), style_body))
        story.append(Spacer(1, 4))

        # Paragraph 2: Bulleted Proof Points
        story.append(Paragraph("<b>Relevant Distributed Systems & Cloud Achievements:</b>", style_body))
        for pt in data.proof_points:
            story.append(Paragraph(f"• {_clean(pt)}", style_bullet))
        story.append(Spacer(1, 4))

        # Paragraph 3: Strategic Alignment & Closing
        story.append(Paragraph(_clean(data.alignment_closing), style_body))
        story.append(Spacer(1, 8))

        # Sign-off
        for line in data.sign_off.strip().split("\n"):
            story.append(Paragraph(_clean(line), style_signoff))

        doc.build(story)
        return out_path
