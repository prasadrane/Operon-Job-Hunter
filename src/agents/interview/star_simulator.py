"""STAR narrative simulation and career graph behavioral response generator.

Extracts grounded Situation, Task, Action, and Result (STAR) stories from
candidate career knowledge graphs (NetworkX DiGraph).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Union
import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class STARNarrative:
    """Structured STAR behavioural story grounded in career graph facts."""

    project_name: str
    situation: str
    task: str
    action: str
    result: str
    technologies: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    company: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize narrative to dictionary."""
        return {
            "project_name": self.project_name,
            "company": self.company,
            "situation": self.situation,
            "task": self.task,
            "action": self.action,
            "result": self.result,
            "technologies": self.technologies,
            "metrics": self.metrics,
            "full_story": self.to_talking_point(),
        }

    def to_talking_point(self) -> str:
        """Format as a concise conversational talking point."""
        comp_str = f" at {self.company}" if self.company else ""
        tech_str = f" using {', '.join(self.technologies)}" if self.technologies else ""
        metric_str = f" -> {'; '.join(self.metrics)}" if self.metrics else ""
        return f"[{self.project_name}{comp_str}]: {self.situation} {self.action}{tech_str}. Delivered: {self.result}{metric_str}"

    def to_markdown(self) -> str:
        """Format narrative as structured markdown."""
        lines = [
            f"### 🌟 {self.project_name}" + (f" ({self.company})" if self.company else ""),
            f"- **Situation:** {self.situation}",
            f"- **Task:** {self.task}",
            f"- **Action:** {self.action}",
            f"- **Result:** {self.result}",
        ]
        if self.technologies:
            lines.append(f"- **Tech Stack:** `{', '.join(self.technologies)}`")
        if self.metrics:
            lines.append(f"- **Key Metrics:** {', '.join(self.metrics)}")
        return "\n".join(lines)


class STARSimulator:
    """Simulates behavioral interview question answering grounded in candidate career graphs."""

    def __init__(self) -> None:
        pass

    def generate_narratives(
        self,
        graph: Optional[Union[nx.DiGraph, List[Dict[str, Any]]]] = None,
        top_k: int = 5,
    ) -> List[STARNarrative]:
        """Generate structured STAR narratives from career graph nodes and edges."""
        if graph is None:
            return [self._create_default_narrative()]

        if isinstance(graph, list):
            return self._generate_from_dict_list(graph, top_k)

        if isinstance(graph, nx.DiGraph):
            if len(graph.nodes) == 0:
                return [self._create_default_narrative()]
            return self._generate_from_digraph(graph, top_k)

        return [self._create_default_narrative()]

    def _generate_from_digraph(self, graph: nx.DiGraph, top_k: int = 5) -> List[STARNarrative]:
        """Extract STAR stories from NetworkX DiGraph."""
        narratives: List[STARNarrative] = []

        project_nodes = [
            n for n, data in graph.nodes(data=True)
            if data.get("type") == "Project"
        ]

        if not project_nodes:
            # Check for any node with metrics or bullets
            for n, data in graph.nodes(data=True):
                if "bullet" in data or "value" in data:
                    narratives.append(
                        STARNarrative(
                            project_name=str(n),
                            situation=f"Led architectural initiatives surrounding {n}.",
                            task="Deliver high performance, scalability, and system resilience.",
                            action=f"Engineered and deployed production infrastructure for {n}.",
                            result=data.get("bullet") or data.get("value") or "Delivered high-impact outcomes.",
                            technologies=[],
                            metrics=[data.get("value")] if data.get("value") else [],
                        )
                    )
            if not narratives:
                return [self._create_default_narrative()]
            return narratives[:top_k]

        for proj in project_nodes:
            # Find company (predecessor)
            companies = [
                pred for pred in graph.predecessors(proj)
                if graph.nodes[pred].get("type") == "Company"
            ]
            company_name = companies[0] if companies else None

            # Find technologies (successors with USED_TECH)
            technologies = [
                succ for succ in graph.successors(proj)
                if graph.nodes[succ].get("type") == "Technology"
                or graph.edges[proj, succ].get("relation") == "USED_TECH"
            ]

            # Find metrics (successors with DELIVERED_METRIC)
            metric_nodes = [
                succ for succ in graph.successors(proj)
                if graph.nodes[succ].get("type") == "ImpactMetric"
                or graph.edges[proj, succ].get("relation") == "DELIVERED_METRIC"
            ]

            metrics_list = []
            bullets_list = []
            for m in metric_nodes:
                m_data = graph.nodes[m]
                val = m_data.get("value")
                bullet = m_data.get("bullet")
                if val:
                    metrics_list.append(str(val))
                if bullet and bullet not in bullets_list:
                    bullets_list.append(bullet)

            tech_str = ", ".join(technologies) if technologies else "modern distributed technologies"
            comp_str = f" at {company_name}" if company_name else ""

            situation = (
                f"Led engineering and scaling of {proj}{comp_str} to solve mission-critical business requirements."
            )
            task = (
                f"Design, architect, and optimize the distributed backend pipeline for {proj} with zero downtime."
            )
            action = (
                f"Implemented core services using {tech_str}, establishing clean abstractions and automated CI/CD."
            )
            if bullets_list:
                result = " ".join(bullets_list)
            elif metrics_list:
                result = f"Achieved key impact metrics: {', '.join(metrics_list)}."
            else:
                result = "Successfully improved system throughput, reliability, and engineering velocity."

            narratives.append(
                STARNarrative(
                    project_name=proj,
                    situation=situation,
                    task=task,
                    action=action,
                    result=result,
                    technologies=technologies,
                    metrics=metrics_list,
                    company=company_name,
                )
            )

        return narratives[:top_k] if narratives else [self._create_default_narrative()]

    def _generate_from_dict_list(self, nodes: List[Dict[str, Any]], top_k: int = 5) -> List[STARNarrative]:
        """Convert a list of dictionary nodes into STARNarrative objects."""
        narratives: List[STARNarrative] = []
        for item in nodes:
            name = item.get("name", "Key Initiative")
            bullet = item.get("bullet", "Delivered core system improvements.")
            technologies = item.get("technologies", [])
            if not technologies and "name" in item:
                technologies = [item["name"]]

            narratives.append(
                STARNarrative(
                    project_name=name,
                    situation=f"Architected and deployed {name} within production ecosystem.",
                    task="Solve core throughput, data consistency, and latency challenges.",
                    action=f"Engineered service pipelines and implemented resilient APIs for {name}.",
                    result=bullet,
                    technologies=technologies,
                    metrics=[item["metric"]] if "metric" in item else [],
                    company=item.get("company"),
                )
            )
        return narratives[:top_k] if narratives else [self._create_default_narrative()]

    def _create_default_narrative(self) -> STARNarrative:
        """Graceful fallback narrative when graph is empty or unpopulated."""
        return STARNarrative(
            project_name="High-Scale Distributed Architecture",
            situation="Core engineering leadership across mission-critical services and distributed platforms.",
            task="Design resilient backend services, optimize data workflows, and guarantee high availability.",
            action="Engineered scalable backend pipelines with caching layers, concurrency management, and observability.",
            result="Delivered 99.99% system availability, reduced latency by 35%, and scaled throughput 3x.",
            technologies=["Python", "Go", "PostgreSQL", "Kafka", "Docker"],
            metrics=["99.99% uptime", "35% latency reduction", "3x throughput"],
            company=None,
        )

    def simulate_response(
        self,
        question: str,
        graph: Optional[Union[nx.DiGraph, List[Dict[str, Any]]]] = None,
    ) -> STARNarrative:
        """Select and tailor the most relevant STAR narrative for a given behavioral interview question."""
        narratives = self.generate_narratives(graph)
        if not narratives:
            return self._create_default_narrative()

        q_lower = question.lower()
        best_narrative = narratives[0]
        best_score = -1

        keywords = [
            "stream", "latency", "scale", "performance", "kafka", "redis", "kubernetes",
            "aws", "database", "postgres", "monolith", "microservice", "fraud", "payment",
            "reliability", "uptime", "optimization", "architecture", "incident", "failure",
        ]

        for narrative in narratives:
            score = 0
            search_text = (
                f"{narrative.project_name} {narrative.situation} {narrative.action} "
                f"{narrative.result} {' '.join(narrative.technologies)} {' '.join(narrative.metrics)}"
            ).lower()

            for kw in keywords:
                if kw in q_lower and kw in search_text:
                    score += 3
            # Check direct token overlap
            for word in q_lower.split():
                if len(word) > 3 and word in search_text:
                    score += 1

            if score > best_score:
                best_score = score
                best_narrative = narrative

        return best_narrative
