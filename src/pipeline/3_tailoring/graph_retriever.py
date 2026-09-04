"""GraphRAG knowledge engine and master career story retriever.

Retrieves verified STAR stories, impact metrics, and technology entities from the candidate's
master resume data store to ground resume tailoring and cover letter generation.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from .hybrid_graph_retriever import HybridGraphRetriever

logger = logging.getLogger(__name__)

def _default_master_resume_path() -> str:
    from src.core.config import get_settings
    return str(get_settings().master_resume_md_path)


DEFAULT_MASTER_RESUME_PATH = "./data/MASTER_RESUME.md"


class GraphRetriever:
    """Retrieves verified candidate achievements, STAR stories, and tech skills from Master Resume."""

    def __init__(self, master_resume_path: Optional[str] = None) -> None:
        self.master_resume_path = Path(
            master_resume_path or _default_master_resume_path())
        self._content = ""
        self._parsed_stories: List[Dict[str, Any]] = []
        self._hybrid_retriever: Optional[HybridGraphRetriever] = None
        self._load_and_index()

    def _load_and_index(self) -> None:
        """Load MASTER_RESUME.md and extract structured stories, skills, and bullets."""
        if not self.master_resume_path.exists():
            logger.warning(
                "Master resume file not found at %s. GraphRetriever using empty state.",
                self.master_resume_path,
            )
            return

        self._content = self.master_resume_path.read_text(encoding="utf-8")
        self._index_stories()

    def _index_stories(self) -> None:
        """Parse H4 story headers and bullet points from markdown with strict section and company boundary isolation."""
        lines = self._content.splitlines()
        current_story_title = ""
        current_story_bullets: List[str] = []
        current_company = ""
        current_role = ""

        def flush_story() -> None:
            nonlocal current_story_title, current_story_bullets
            if current_story_title and current_story_bullets:
                self._parsed_stories.append({
                    "story_title": current_story_title,
                    "title": current_story_title,
                    "company": current_company,
                    "role": current_role,
                    "bullets": current_story_bullets[:],
                    "content": "\n".join(current_story_bullets),
                })
            current_story_title = ""
            current_story_bullets = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Major section change (e.g. ## Technical Projects, ## Education, ## Skills)
            if line_str.startswith("## "):
                flush_story()
                sec_header = line_str.lstrip("#").strip().lower()
                if not ("experience" in sec_header or "story" in sec_header):
                    current_company = ""
                    current_role = ""
                continue

            # Role & Company header: e.g. ### **Software Developer** - *London Computer Systems*
            clean_norm = line_str.replace("\u2014", " - ").replace("\u2013", " - ").replace("—", " - ").replace("–", " - ")
            clean_h = re.sub(r"^#+\s*", "", clean_norm).replace("*", "").strip()

            if " - " in clean_norm and (line_str.startswith("#") and not line_str.startswith("####")) and not clean_h.lower().startswith("story"):
                parts = re.split(r"\s*-\s*", clean_h, maxsplit=1)
                if len(parts) == 2 and parts[0].lower() not in ["projects", "experience", "education", "skills", "certifications", "canonical summary", "domain-specific summary variants"]:
                    flush_story()
                    current_role = parts[0].strip()
                    current_company = parts[1].strip()
                    continue

            # Story header: e.g. #### Story 1 - Observability & Fannie Mae Integration
            if line_str.startswith("#### Story") or (line_str.startswith("### Story") and "story" in line_str.lower()):
                flush_story()
                current_story_title = line_str.lstrip("#").strip()
                current_story_bullets = []
                continue

            # Bullet points attached to current story
            if line_str.startswith("- ") or line_str.startswith("* ") or line_str.startswith("• "):
                clean_bullet = line_str.lstrip("*- •").strip()
                if current_story_title:
                    current_story_bullets.append(clean_bullet)

        flush_story()

    def get_master_content(self) -> str:
        """Return the raw markdown content of the master resume."""
        return self._content

    def retrieve_evidence(
        self,
        target_skills: List[str],
        target_company: Optional[str] = None,
        max_evidence: int = 5,
    ) -> List[str]:
        """Retrieve verified candidate achievements and metrics matching target skills."""
        if not target_skills and not self._content:
            return []

        evidence_found: List[str] = []
        skill_patterns = [
            re.compile(rf"\b{re.escape(s.strip())}\b", re.IGNORECASE)
            for s in target_skills
            if len(s.strip()) > 1
        ]

        # Scan all parsed stories for matching skills
        for story in self._parsed_stories:
            for bullet in story["bullets"]:
                if any(pat.search(bullet) for pat in skill_patterns):
                    if bullet not in evidence_found:
                        evidence_found.append(bullet)
                        if len(evidence_found) >= max_evidence:
                            return evidence_found

        # If not enough found via strict regex, search all bullets in content
        if len(evidence_found) < max_evidence:
            for line in self._content.splitlines():
                line_clean = line.strip().lstrip("*- •").strip()
                if (line.strip().startswith("- ") or line.strip().startswith("* ")) and any(
                    pat.search(line_clean) for pat in skill_patterns
                ):
                    if line_clean not in evidence_found:
                        evidence_found.append(line_clean)
                        if len(evidence_found) >= max_evidence:
                            break

        # Fallback baseline evidence from master history if no specific matches
        if not evidence_found and self._parsed_stories:
            for story in self._parsed_stories:
                for bullet in story["bullets"]:
                    evidence_found.append(bullet)
                    if len(evidence_found) >= max_evidence:
                        break
                if len(evidence_found) >= max_evidence:
                    break

        return evidence_found[:max_evidence]

    def retrieve_stories(
        self,
        target_skills: List[str],
        max_stories: int = 3,
    ) -> List[Dict[str, Any]]:
        """Retrieve top STAR stories ranked by Hybrid GraphRAG multi-hop relevance."""
        if not self._parsed_stories:
            return []

        # 1. Primary: Hybrid GraphRAG Personalized PageRank retrieval
        try:
            if not self._hybrid_retriever and self.master_resume_path.exists():
                self._hybrid_retriever = HybridGraphRetriever(
                    master_resume_path=str(self.master_resume_path))

            if self._hybrid_retriever and target_skills:
                query = " ".join(target_skills)
                subgraphs = self._hybrid_retriever.retrieve_story_subgraphs(
                    query, max_stories=max_stories)
                if subgraphs:
                    results = []
                    for sg in subgraphs:
                        bullets = sg.get("bullets", [])
                        results.append({
                            "story_title": sg.get("title", ""),
                            "title": sg.get("title", ""),
                            "company": sg.get("company", ""),
                            "role": sg.get("role", ""),
                            "bullets": bullets,
                            "content": "\n".join(bullets),
                            "technologies": sg.get("technologies", []),
                            "metrics": sg.get("metrics", []),
                        })
                    return results
        except Exception as e:
            logger.debug(
                "Hybrid retriever error: %s. Falling back to keyword ranker.", e)

        # 2. Fallback: Keyword overlap ranking
        scored_stories: List[tuple[int, Dict[str, Any]]] = []
        skill_patterns = [
            re.compile(rf"\b{re.escape(s.strip())}\b", re.IGNORECASE)
            for s in target_skills
            if len(s.strip()) > 1
        ]

        for story in self._parsed_stories:
            score = 0
            text = f"{story['title']}\n{story['content']}"
            for pat in skill_patterns:
                if pat.search(text):
                    score += 1
            scored_stories.append((score, story))

        scored_stories.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored_stories[:max_stories]]

    def get_top_metrics(self) -> List[str]:
        """Extract all verified quantitative impact metrics from master resume."""
        metric_pattern = re.compile(
            r"(\b\d+(?:\.\d+)?%\b|\$\d+(?:\.\d+)?\s*(?:M|K|B|million|thousand)?\b|\b\d+[kK]\+?\s*req|\b\d+[mM]\+?\s*events|\b\d+\s*engineering hours|\b99\.9\d*%\b|\b<3s\b|\b45s\b|\b40%\b|\b70%\b|\b80%\b|\b60%\b)",
            re.IGNORECASE,
        )
        metrics: List[str] = []
        for line in self._content.splitlines():
            line_clean = line.strip().lstrip("*- •").strip()
            if metric_pattern.search(line_clean):
                matches = metric_pattern.findall(line_clean)
                for m in matches:
                    if m not in metrics:
                        metrics.append(m)

        return metrics

    def get_verified_skills(self) -> List[str]:
        """Extract list of verified technical skills from the Skills section."""
        skills: List[str] = []
        in_skills = False
        for line in self._content.splitlines():
            line_str = line.strip()
            if "Technical Skills" in line_str:
                in_skills = True
                continue
            if in_skills and line_str.startswith("## "):
                in_skills = False
                break
            if in_skills and (line_str.startswith("- ") or line_str.startswith("* ")):
                # e.g. - **Languages**: C#, Python, TypeScript
                clean_line = line_str.lstrip("*- •").strip()
                if ":" in clean_line:
                    _, items_str = clean_line.split(":", 1)
                    items = [it.strip()
                             for it in items_str.split(",") if it.strip()]
                    skills.extend(items)
                else:
                    skills.append(clean_line)

        return skills

    def get_hierarchical_communities(self) -> List[Dict[str, Any]]:
        """Retrieve macro capability communities and thematic summaries."""
        if not self._hybrid_retriever and self.master_resume_path.exists():
            self._hybrid_retriever = HybridGraphRetriever(master_resume_path=str(self.master_resume_path))
        if self._hybrid_retriever:
            return self._hybrid_retriever.get_hierarchical_communities()
        return []

    def retrieve_causal_paths(self, target_skills: List[str], max_paths: int = 3) -> List[Dict[str, Any]]:
        """Retrieve explainable multi-hop causal reasoning chains."""
        if not self._hybrid_retriever and self.master_resume_path.exists():
            self._hybrid_retriever = HybridGraphRetriever(master_resume_path=str(self.master_resume_path))
        if self._hybrid_retriever and target_skills:
            query = " ".join(target_skills)
            return self._hybrid_retriever.retrieve_causal_paths(query, max_paths=max_paths)
        return []

    def retrieve_rrf(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve nodes using Tri-Hybrid Reciprocal Rank Fusion."""
        if not self._hybrid_retriever and self.master_resume_path.exists():
            self._hybrid_retriever = HybridGraphRetriever(master_resume_path=str(self.master_resume_path))
        if self._hybrid_retriever:
            return self._hybrid_retriever.retrieve_rrf(query, top_k=top_k)
        return []

    def bridge_skill_gaps(self, jd_skills: List[str]) -> Dict[str, Any]:
        """Perform 1-hop ontology reasoning to bridge target JD skills."""
        if not self._hybrid_retriever and self.master_resume_path.exists():
            self._hybrid_retriever = HybridGraphRetriever(master_resume_path=str(self.master_resume_path))
        if self._hybrid_retriever:
            return self._hybrid_retriever.bridge_skill_gaps(jd_skills)
        return {"direct_matches": [], "transferable_bridges": [], "bridging_statements": [], "unmatched_gaps": []}

    def get_longitudinal_competencies(self) -> List[Dict[str, Any]]:
        """Retrieve multi-year cross-project competencies."""
        if not self._hybrid_retriever and self.master_resume_path.exists():
            self._hybrid_retriever = HybridGraphRetriever(master_resume_path=str(self.master_resume_path))
        if self._hybrid_retriever:
            return self._hybrid_retriever.get_longitudinal_competencies()
        return []

    def generate_interview_prep_packet(self, target_skills: List[str]) -> List[Dict[str, Any]]:
        """Generate targeted behavioral & system design questions and grounded model answers."""
        if not self._hybrid_retriever and self.master_resume_path.exists():
            self._hybrid_retriever = HybridGraphRetriever(master_resume_path=str(self.master_resume_path))
        if self._hybrid_retriever:
            return self._hybrid_retriever.generate_interview_prep_packet(target_skills)
        return []

    def retrieve_atomic_proofs(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve single-line, highly quantified atomic proof points."""
        if not self._hybrid_retriever and self.master_resume_path.exists():
            self._hybrid_retriever = HybridGraphRetriever(master_resume_path=str(self.master_resume_path))
        if self._hybrid_retriever:
            return self._hybrid_retriever.retrieve_atomic_proofs(query, top_k=top_k)
        return []

    def retrieve_star_narratives(self, query: str, max_stories: int = 3) -> List[Dict[str, Any]]:
        """Retrieve complete 5-part STAR+R structures."""
        if not self._hybrid_retriever and self.master_resume_path.exists():
            self._hybrid_retriever = HybridGraphRetriever(master_resume_path=str(self.master_resume_path))
        if self._hybrid_retriever:
            return self._hybrid_retriever.retrieve_star_narratives(query, max_stories=max_stories)
        return []

    def retrieve_longitudinal_arcs(self, query: str = "") -> List[Dict[str, Any]]:
        """Retrieve multi-year cumulative domain mastery statements."""
        if not self._hybrid_retriever and self.master_resume_path.exists():
            self._hybrid_retriever = HybridGraphRetriever(master_resume_path=str(self.master_resume_path))
        if self._hybrid_retriever:
            return self._hybrid_retriever.retrieve_longitudinal_arcs(query)
        return []

    def get_competency_profile(self) -> List[Dict[str, Any]]:
        """Aggregate candidate achievements across enterprise competency dimensions."""
        if not self._hybrid_retriever and self.master_resume_path.exists():
            self._hybrid_retriever = HybridGraphRetriever(master_resume_path=str(self.master_resume_path))
        if self._hybrid_retriever:
            return self._hybrid_retriever.get_competency_profile()
        return []




