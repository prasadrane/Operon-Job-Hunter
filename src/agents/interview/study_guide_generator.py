"""Interview Intelligence & Tailored Study Guide Copilot.

Produces structured 3-track interview preparation packets:
- Track 1: System Design Architectures & Deep Dives
- Track 2: Graph-Grounded Behavioral STAR Narratives
- Track 3: Reverse-Interview Technical Questions

Formats output as structured Markdown packets ready for Telegram attachments and web visualizers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Union
import networkx as nx

from src.agents.interview.star_simulator import STARSimulator, STARNarrative

logger = logging.getLogger(__name__)


@dataclass
class StudyGuide:
    """Structured container for 3-track interview preparation guide."""

    job_title: str
    company: str
    system_design_topics: List[str]
    behavioral_star_talking_points: List[str]
    reverse_interview_questions: List[str]
    star_narratives: List[STARNarrative] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    markdown_guide: str = ""

    def __getitem__(self, item: str) -> Any:
        """Provide dictionary subscript compatibility."""
        return self.to_dict()[item]

    def __contains__(self, item: str) -> bool:
        """Provide dictionary contains compatibility."""
        return item in self.to_dict()

    def get(self, key: str, default: Any = None) -> Any:
        """Provide dict.get compatibility."""
        return self.to_dict().get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize study guide to dictionary."""
        return {
            "company": self.company,
            "job_title": self.job_title,
            "system_design_topics": self.system_design_topics,
            "behavioral_star_talking_points": self.behavioral_star_talking_points,
            "reverse_interview_questions": self.reverse_interview_questions,
            "star_narratives": [n.to_dict() for n in self.star_narratives],
            "metadata": self.metadata,
            "markdown_guide": self.markdown_guide,
        }


class StudyGuideGenerator:
    """Generates personalized 3-track interview preparation packets grounded in candidate career graphs."""

    def __init__(self, star_simulator: Optional[STARSimulator] = None) -> None:
        self.star_simulator = star_simulator or STARSimulator()

    def _curate_system_design_topics(
        self, job_title: str, company: str, job_description: Optional[str] = None
    ) -> List[str]:
        """Curate focused System Design topics tailored to role, company, and JD."""
        jd_text = (job_description or "").lower()
        title_text = job_title.lower()

        topics = [
            "System Design Architecture: Event-driven pub/sub scaling & streaming ingestion (Kafka/Pulsar)",
            "High availability, partition tolerance, consensus, and cache consistency (Redis/Memcached)",
            "Distributed database sharding, replication topologies, and ACID vs BASE trade-offs",
            "API Gateway routing, rate limiting, circuit breaker patterns, and token-bucket throttling",
        ]

        if "infra" in title_text or "kubernetes" in jd_text or "cloud" in jd_text:
            topics.append("Multi-region Kubernetes deployment orchestration, service mesh (Istio), and autoscaling")

        if "payment" in jd_text or "fintech" in jd_text or "stripe" in company.lower():
            topics.append("Idempotent payment processing pipelines and distributed 2-Phase Commit (2PC) transactions")

        if "stream" in jd_text or "netflix" in company.lower() or "uber" in company.lower():
            topics.append("Ultra-low-latency real-time stream aggregation, backpressure handling, and sliding window telemetry")

        return topics

    def _curate_reverse_interview_questions(
        self, job_title: str, company: str, job_description: Optional[str] = None
    ) -> List[str]:
        """Generate high-signal reverse interview questions for the candidate to ask interviewers."""
        jd_text = (job_description or "").lower()

        questions = [
            f"How does the engineering team at {company} manage technical debt and cross-team architectural RFCs for {job_title} initiatives?",
            f"What are the primary operational latency and throughput bottlenecks your infrastructure currently faces at peak load?",
            f"How is observability, distributed tracing, and incident post-mortem culture structured across production services at {company}?",
            f"What does the 6-12 month architectural roadmap look like for the core systems this role will own?",
            f"How do you evaluate trade-offs between consistency and availability in your distributed data layers?",
        ]

        if "kubernetes" in jd_text or "cloud" in jd_text:
            questions.append(f"What does your multi-region failover and disaster recovery strategy look like across cloud providers?")

        return questions

    def generate_interview_prep(
        self,
        job_title: str,
        company: str,
        graph: Optional[nx.DiGraph] = None,
        graph_nodes: Optional[Union[List[Dict[str, Any]], nx.DiGraph]] = None,
        job_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a complete 3-track interview preparation packet."""
        # Resolve graph input
        effective_graph = graph if graph is not None else graph_nodes

        # Generate STAR narratives
        narratives = self.star_simulator.generate_narratives(effective_graph)

        # Extract talking points
        star_talking_points = []
        if isinstance(effective_graph, list) and not isinstance(effective_graph, nx.DiGraph):
            for n in effective_graph:
                if isinstance(n, dict):
                    if "bullet" in n:
                        star_talking_points.append(f"Story: {n.get('name', 'Initiative')} -> {n['bullet']}")
                    elif "name" in n:
                        star_talking_points.append(f"Story: {n['name']}")
        if not star_talking_points:
            star_talking_points = [n.to_talking_point() for n in narratives]

        # Curate tracks
        sys_design = self._curate_system_design_topics(job_title, company, job_description)
        reverse_questions = self._curate_reverse_interview_questions(job_title, company, job_description)

        metadata = {
            "company": company,
            "job_title": job_title,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_star_stories": len(narratives),
            "tracks_included": ["System Design", "Behavioral STAR", "Reverse Questions"],
        }

        guide_obj = StudyGuide(
            job_title=job_title,
            company=company,
            system_design_topics=sys_design,
            behavioral_star_talking_points=star_talking_points,
            reverse_interview_questions=reverse_questions,
            star_narratives=narratives,
            metadata=metadata,
        )

        guide_dict = guide_obj.to_dict()
        markdown_packet = self.format_markdown_packet(guide_dict)
        guide_dict["markdown_guide"] = markdown_packet
        return guide_dict

    def format_markdown_packet(self, prep_data: Dict[str, Any]) -> str:
        """Format 3-track interview preparation packet into clean Markdown for Telegram attachments."""
        company = prep_data.get("company", "Target Company")
        job_title = prep_data.get("job_title", "Software Engineer")
        sys_design = prep_data.get("system_design_topics", [])
        star_points = prep_data.get("behavioral_star_talking_points", [])
        reverse_questions = prep_data.get("reverse_interview_questions", [])
        star_narratives = prep_data.get("star_narratives", [])

        md_lines = [
            f"# Interview Intelligence & Study Guide: {job_title} @ {company}",
            "",
            "> **Interview Track Pack** | Generated by CareerGraph-AI Interview Copilot",
            f"> **Target Company:** {company} | **Role:** {job_title}",
            "",
            "---",
            "",
            "## Track 1: System Design Architectures & Deep Dives",
            "Key architectural paradigms and technical deep-dives to review before the technical interview rounds:",
            "",
        ]

        for i, topic in enumerate(sys_design, 1):
            md_lines.append(f"{i}. **{topic}**")

        md_lines.extend([
            "",
            "---",
            "",
            "## Track 2: Graph-Grounded Behavioral STAR Narratives",
            "Verified candidate career stories mapped to Situation, Task, Action, and Result:",
            "",
        ])

        if star_narratives:
            for item in star_narratives:
                if isinstance(item, dict):
                    proj = item.get("project_name", "Initiative")
                    comp = f" ({item.get('company')})" if item.get("company") else ""
                    md_lines.append(f"### 🌟 {proj}{comp}")
                    md_lines.append(f"- **Situation:** {item.get('situation', '')}")
                    md_lines.append(f"- **Task:** {item.get('task', '')}")
                    md_lines.append(f"- **Action:** {item.get('action', '')}")
                    md_lines.append(f"- **Result:** {item.get('result', '')}")
                    if item.get("technologies"):
                        md_lines.append(f"- **Tech Stack:** `{', '.join(item['technologies'])}`")
                    if item.get("metrics"):
                        md_lines.append(f"- **Key Metrics:** {', '.join(item['metrics'])}")
                    md_lines.append("")
        else:
            for pt in star_points:
                md_lines.append(f"- {pt}")
            md_lines.append("")

        md_lines.extend([
            "---",
            "",
            "## Track 3: Reverse-Interview Technical Questions",
            f"High-impact questions to ask engineering leads and hiring managers at {company}:",
            "",
        ])

        for i, q in enumerate(reverse_questions, 1):
            md_lines.append(f"{i}. {q}")

        md_lines.extend([
            "",
            "---",
            "",
            "*Generated by CareerGraph-AI Interview Copilot — Phase 3 Autonomous Copilot Engine*",
        ])

        return "\n".join(md_lines)
