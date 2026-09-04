"""Online Assessment (OA) Radar: Detects incoming coding assessments and generates prep packs."""

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OA_PLATFORMS = [
    "HackerRank",
    "CodeSignal",
    "Karat",
    "Byteboard",
    "Coderbyte",
    "Codility",
    "TestGorilla",
    "Filtered",
]


@dataclass
class OADetectionResult:
    is_oa: bool = False
    platform: str = ""
    company: str = ""
    role: str = ""
    deadline: Optional[str] = None
    test_link: Optional[str] = None
    study_guide_path: Optional[str] = None
    raw_details: Dict[str, Any] = field(default_factory=dict)


class OARadar:
    """Scans incoming recruitment messages for technical coding assessments and triggers study guides."""

    def __init__(self, artifacts_dir: Optional[str] = None) -> None:
        self.artifacts_dir = Path(artifacts_dir or "./data/artifacts")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def scan_email(
        self,
        subject: str,
        body: str,
        sender: str = "",
    ) -> OADetectionResult:
        """Analyze email subject and body for technical assessment indicators."""
        combined_text = f"{subject}\n{body}\n{sender}"
        combined_lower = combined_text.lower()

        is_assessment = any(kw in combined_lower for kw in [
            "assessment", "codesignal", "hackerrank", "karat", "codility",
            "coding challenge", "technical assessment", "online test", "take-home",
        ])

        if not is_assessment:
            return OADetectionResult(is_oa=False)

        # 1. Identify platform
        matched_platform = "Online Assessment"
        for plat in OA_PLATFORMS:
            if plat.lower() in combined_lower:
                matched_platform = plat
                break

        # 2. Extract company name
        company = ""
        # Try from sender domain e.g. recruiting@stripe.com
        if "@" in sender:
            domain_part = sender.split("@")[-1].split(".")[0]
            if domain_part.lower() not in ["codesignal", "hackerrank", "gmail", "outlook", "greenhouse", "lever", "ashby"]:
                company = domain_part.capitalize()

        if not company:
            # Match company from subject or body: e.g. "Stripe Online Assessment"
            comp_match = re.search(r"([A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)?)\s+(?:Online Assessment|Technical Assessment|CodeSignal|HackerRank)", subject)
            if comp_match:
                company = comp_match.group(1).strip()
            else:
                comp_match2 = re.search(r"(?:for|at)\s+([A-Z][a-z0-9]+)", combined_text)
                if comp_match2:
                    company = comp_match2.group(1).strip()

        # 3. Extract test URL
        test_link = None
        urls = re.findall(r"https?://[^\s<>\"')]+", body)
        for u in urls:
            if any(p.lower() in u.lower() for p in OA_PLATFORMS) or "test" in u.lower() or "assessment" in u.lower():
                test_link = u
                break
        if not test_link and urls:
            test_link = urls[0]

        # 4. Extract deadline if stated
        deadline = None
        deadline_match = re.search(r"(?:within|in|by)\s+(\d+\s+(?:days?|hours?|business days?))", body, re.IGNORECASE)
        if deadline_match:
            deadline = deadline_match.group(1).strip()

        return OADetectionResult(
            is_oa=True,
            platform=matched_platform,
            company=company or "Employer",
            test_link=test_link,
            deadline=deadline,
            raw_details={"subject": subject, "sender": sender},
        )

    def generate_prep_guide(self, detection: OADetectionResult) -> Dict[str, Any]:
        """Generate structured interview study guide and high-yield topic recommendations."""
        platform = detection.platform
        company = detection.company
        role = detection.role or "Software Engineer"

        topics_map = {
            "HackerRank": [
                "Data Structures: HashMaps, Heaps, Tree Traversals",
                "Algorithms: Sliding Window, Two Pointers, Dynamic Programming",
                "SQL Query Optimization (T-SQL / Postgres)",
                "String Parsing & Prefix Trees (Trie)",
            ],
            "CodeSignal": [
                "Task 1-2: Speed & Implementation Basics (Array/String manipulation)",
                "Task 3: Matrix Transformations / Simulation",
                "Task 4: Hard Algorithm / Prefix Sums / Tree Traversal",
                "Edge Case Handling & Test Suite Optimization",
            ],
            "Karat": [
                "Question 1: Pure Coding / Fast Implementation",
                "Question 2: Graph Traversal / BFS/DFS or Grid Simulation",
                "System Architecture / Code Review debugging discussion",
            ],
        }

        recommended_topics = topics_map.get(platform, [
            "Data Structures & Algorithms",
            "Concurrency & Thread Synchronization",
            "System Design Principles",
            "Database Indexing & Query Tuning",
        ])

        title = f"{company} — {platform} Technical Preparation Guide"
        content = (
            f"# {title}\n\n"
            f"**Target Role:** {role}\n"
            f"**Platform:** {platform}\n"
            f"**Test Link:** {detection.test_link or 'See Email'}\n\n"
            f"## Strategic Focus Topics:\n"
            + "\n".join(f"- {top}" for top in recommended_topics)
            + f"\n\n## Assessment Strategy:\n"
            f"1. Read all problems completely before coding.\n"
            f"2. Validate constraints and test boundary inputs (null, empty, $10^5$ items).\n"
            f"3. Prioritize clean, modular code with descriptive variable naming."
        )

        return {
            "title": title,
            "company": company,
            "platform": platform,
            "content": content,
            "recommended_topics": recommended_topics,
        }

    def scan_and_trigger_prep(
        self,
        subject: str,
        body: str,
        sender: str = "",
    ) -> OADetectionResult:
        """Scan incoming email and automatically stage a study guide file if an OA is detected."""
        detection = self.scan_email(subject, body, sender)
        if detection.is_oa:
            guide = self.generate_prep_guide(detection)
            safe_company = re.sub(r"[^\w\-]", "_", detection.company or "Company")
            filepath = self.artifacts_dir / f"{safe_company}_study_guide.md"
            filepath.write_text(guide["content"], encoding="utf-8")
            detection.study_guide_path = str(filepath.resolve())
            logger.info("Auto-generated OA study guide for %s: %s", detection.company, filepath)
        return detection
