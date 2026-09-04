"""Recruiter Discovery & Hiring Manager Finder Agent.

Performs Graph-Intersection retrieval between target job requirements and the candidate's
verified career graph, and constructs boolean search operators for recruiter & hiring manager discovery.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set
import networkx as nx

logger = logging.getLogger(__name__)

# Standard management & talent acquisition keywords
BASE_MANAGEMENT_KEYWORDS = [
    "Engineering Manager",
    "Director of Engineering",
    "Head of Engineering",
    "VP of Engineering",
    "Technical Lead",
    "Lead Engineer",
]

BASE_RECRUITER_KEYWORDS = [
    "Technical Recruiter",
    "Senior Technical Recruiter",
    "Talent Acquisition Lead",
    "Engineering Recruiter",
    "Senior Tech Sourcer",
]


class RecruiterFinder:
    """Discovers hiring managers and matches candidate graph capabilities to target JD."""

    def __init__(self) -> None:
        pass

    def _extract_domain_from_role(self, role: str) -> str:
        """Extract primary domain specialization from role title (e.g. 'Distributed Systems')."""
        clean_role = re.sub(r"\b(Senior|Staff|Principal|Lead|Junior|Associate|Software|Engineer|Developer|I|II|III|IV)\b", "", role, flags=re.IGNORECASE).strip()
        # Remove extra punctuation
        clean_role = re.sub(r"[\-–—\(\)/]", " ", clean_role).strip()
        return " ".join(clean_role.split())

    def find_hiring_manager_keywords(self, role: str) -> List[str]:
        """Generate targeted search keywords for engineering managers and technical recruiters."""
        keywords: List[str] = []
        domain = self._extract_domain_from_role(role)

        # Add base management keywords
        keywords.extend(BASE_MANAGEMENT_KEYWORDS)

        # Add domain-specific manager keywords
        if domain:
            keywords.append(f"Engineering Manager, {domain}")
            keywords.append(f"Lead {domain} Engineer")
            keywords.append(f"Director of {domain}")

        # Add recruiter keywords
        keywords.extend(BASE_RECRUITER_KEYWORDS)
        if domain:
            keywords.append(f"Technical Recruiter, {domain}")

        return keywords

    def generate_search_queries(self, company: str, role: str) -> List[str]:
        """Generate structured Google/LinkedIn boolean search strings."""
        domain = self._extract_domain_from_role(role)
        domain_query = f'("{domain}")' if domain else '("Engineering")'

        queries = [
            f'site:linkedin.com/in ("{company}") ("Engineering Manager" OR "Director of Engineering" OR "Lead Engineer") {domain_query}',
            f'site:linkedin.com/in ("{company}") ("Technical Recruiter" OR "Talent Acquisition" OR "Engineering Recruiter") {domain_query}',
            f'site:linkedin.com/in ("{company}") ("VP of Engineering" OR "Head of Engineering")',
            f'"{company}" ("Engineering Manager" OR "Lead Engineer") "{role}"',
        ]
        return queries

    def match_graph_intersection(
        self,
        jd_keywords: List[str],
        candidate_graph: nx.DiGraph,
    ) -> List[Dict[str, Any]]:
        """Perform graph-intersection matching between target JD tech keywords and candidate career graph."""
        if not candidate_graph or not jd_keywords:
            return []

        # Index candidate graph technologies
        tech_nodes: Dict[str, Dict[str, Any]] = {}
        for node, data in candidate_graph.nodes(data=True):
            if data.get("type") == "Technology":
                tech_nodes[node.lower()] = {"node": node, "data": data}
                for alias in data.get("aliases", []):
                    tech_nodes[alias.lower()] = {"node": node, "data": data}

        matched_intersections: List[Dict[str, Any]] = []
        seen_canonical: Set[str] = set()

        for kw in jd_keywords:
            clean_kw = kw.strip()
            kw_lower = clean_kw.lower()

            canonical = None
            if kw_lower in tech_nodes:
                canonical = tech_nodes[kw_lower]["node"]
            else:
                for t_key, t_val in tech_nodes.items():
                    if kw_lower == t_key or kw_lower in t_key.split() or t_key in kw_lower.split():
                        canonical = t_val["node"]
                        break

            if canonical:
                if canonical in seen_canonical:
                    continue
                seen_canonical.add(canonical)


                # Find associated projects connected to this technology
                projects: List[str] = []
                metrics: List[str] = []

                # Predecessors in DiGraph where project -> technology (relation="USED_TECH")
                for pred in candidate_graph.predecessors(canonical):
                    pred_data = candidate_graph.nodes[pred]
                    if pred_data.get("type") == "Project":
                        projects.append(pred)
                        # Check if project has associated metrics
                        for succ in candidate_graph.successors(pred):
                            succ_data = candidate_graph.nodes[succ]
                            if succ_data.get("type") == "ImpactMetric":
                                val = succ_data.get("value", succ)
                                metrics.append(val)

                # In case project is a successor or undirected match
                for succ in candidate_graph.successors(canonical):
                    succ_data = candidate_graph.nodes[succ]
                    if succ_data.get("type") == "Project":
                        projects.append(succ)

                matched_intersections.append({
                    "technology": canonical,
                    "matched_keyword": clean_kw,
                    "projects": list(dict.fromkeys(projects)),
                    "metrics": list(dict.fromkeys(metrics)),
                })

        return matched_intersections

    def recommend_star_hook(
        self,
        target_role: str,
        jd_keywords: List[str],
        candidate_graph: nx.DiGraph,
    ) -> str:
        """Synthesize high-impact STAR hook grounded in intersecting graph achievements."""
        intersections = self.match_graph_intersection(jd_keywords, candidate_graph)

        if not intersections:
            return "architected scalable cloud microservices and high-throughput data platforms"

        # Prioritize intersection with metrics
        best_match = None
        for item in intersections:
            if item["metrics"]:
                best_match = item
                break
        if not best_match:
            best_match = intersections[0]

        tech = best_match["technology"]
        metrics = best_match["metrics"]
        projects = best_match["projects"]

        if metrics:
            metric_str = ", ".join(metrics[:2])
            return f"scaled {tech} streaming pipelines with {metric_str}"
        elif projects:
            proj = projects[0]
            return f"architected {tech} systems for {proj}"
        else:
            return f"scaled high-throughput {tech} backend infrastructure"
