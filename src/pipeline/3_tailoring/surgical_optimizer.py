"""Surgical bullet optimizer and ATS keyword bold tag injector.

Bolding rule (minimal, substance-first):
- Bold character ratio cap (<=15% of bullet length, +5% tolerance)
- Max 2 bold phrases per bullet
- Disallows bolding the leading action verb (unless anchor bold enabled)
- Priority: impact metrics > JD-matching tech > anchor (first 3-5 words, opt-in)
- Surgical delta patching and deterministic action verb deduplication micro-linter
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from src.core.constants import COMMON_TECH_KEYWORDS

logger = logging.getLogger(__name__)

# Common action verbs to prevent bolding when leading a bullet
STRONG_ACTION_VERBS = {
    "ARCHITECTED", "ENGINEERED", "SPEARHEADED", "ORCHESTRATED", "DESIGNED",
    "IMPLEMENTED", "DEVELOPED", "MIGRATED", "OPTIMIZED", "RE-ENGINEERED",
    "DIAGNOSED", "REDUCED", "ELIMINATED", "ESTABLISHED", "AUTHORED", "BUILT",
    "RESOLVED", "DELIVERED", "LED", "OWNED", "ACCELERATED", "AUTOMATED",
}

ACTION_VERB_ALTERNATIVES: Dict[str, List[str]] = {
    "Architected": ["Engineered", "Designed", "Spearheaded", "Constructed"],
    "Built": ["Developed", "Engineered", "Implemented", "Constructed"],
    "Designed": ["Architected", "Engineered", "Formulated", "Constructed"],
    "Implemented": ["Deployed", "Executed", "Engineered", "Integrated"],
    "Engineered": ["Architected", "Developed", "Constructed", "Built"],
    "Developed": ["Engineered", "Built", "Authored", "Constructed"],
    "Migrated": ["Transitioned", "Modernized", "Transferred", "Re-engineered"],
    "Optimized": ["Streamlined", "Accelerated", "Enhanced", "Refined"],
    "Led": ["Directed", "Guided", "Spearheaded", "Orchestrated"],
    "Managed": ["Spearheaded", "Directed", "Orchestrated", "Oversaw"],
    "Created": ["Authored", "Established", "Engineered", "Produced"],
    "Reduced": ["Cut", "Minimized", "Decreased", "Curtailed"],
    "Scaled": ["Expanded", "Accelerated", "Amplified", "Grew"],
    "Orchestrated": ["Coordinated", "Engineered", "Spearheaded", "Architected"],
    "Spearheaded": ["Led", "Directed", "Championed", "Guided"],
}


def clean_text_dashes(text: str) -> str:
    """Normalize dashes, em-dashes, and date ranges to standard ASCII."""
    if not text:
        return ""
    # Normalize unicode dashes to standard ASCII hyphen
    text = re.sub(r"[\u2014\u2013\u2015\u2012\u2011\u2010—–―]", " - ", text)
    # Normalize date ranges
    text = re.sub(r"(\b[A-Za-z]{3}\s+\d{4}|\b\d{4})\s*-\s*([A-Za-z]{3}\s+\d{4}|\b\d{4}|\bPresent\b)", r"\1 - \2", text)
    text = re.sub(r"\s+-\s+", " - ", text)
    text = re.sub(r"\s*-\s*-\s*", " - ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


KNOWN_TECH_TERMS: Set[str] = {
    "AWS", "AWS ECS FARGATE", "AWS LAMBDA", "DYNAMODB", "S3", "SQS", "SNS",
    "AMAZON MSK", "KAFKA", "C#", "PYTHON", "TYPESCRIPT", "SQL", "T-SQL",
    "POSTGRESQL", "MYSQL", "SQL SERVER", "LANCEDB", ".NET", ".NET CORE",
    ".NET 6", ".NET 8", ".NET 9", "ASP.NET CORE", "FASTAPI", "GRAPHQL",
    "DOCKER", "KUBERNETES", "TERRAFORM", "ANGULAR", "ANGULAR 18", "RXJS",
    "NGRX", "DYNATRACE", "OPENTELEMETRY", "SPLUNK", "PAGERDUTY", "WINDBG",
    "AMAZON BEDROCK", "CLAUDE SONNET", "GRAPHRAG", "PLAYWRIGHT", "REDIS",
    "FASTGRAPHRAG", "VERCEL", "ILSPY", "SPLIT.IO", "DOTNET-COUNTERS", "DOTNET-DUMP",
}

# Unified case-insensitive tech term lookup (reconciles KNOWN_TECH_TERMS + COMMON_TECH_KEYWORDS)
_TECH_TERMS_UPPER: Set[str] = KNOWN_TECH_TERMS | {kw.upper() for kw in COMMON_TECH_KEYWORDS}


def _is_known_tech(term: str) -> bool:
    """Case-insensitive check whether *term* is a known technology keyword."""
    return term.upper().strip() in _TECH_TERMS_UPPER


# Declarative regex patterns for high-impact metrics and ROI outcomes
IMPACT_PATTERNS = [
    re.compile(r"\b(?:cutting|reduced?|reducing|slashed?|slashing|saving|saved)\s+[^,.;()]+?\b\d+%\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?%\s*(?:uptime|availability|reduction|cost reduction|increase|accuracy|consensus)\b", re.IGNORECASE),
    re.compile(r"\b(?:from\s+\d+\s*\w+\s+to\s+sub-\d+\s*\w+)\b", re.IGNORECASE),
    re.compile(r"\b(?:slash(?:ed)?\s+[^,.;()]+?\s+from\s+\d+s\s+to\s+<\d+s)\b", re.IGNORECASE),
    re.compile(r"\bsub-second\s+(?:routing|query)\s+latency\b", re.IGNORECASE),
    re.compile(r"\b(?:saving|reclaim(?:ing)?)\s+(?:clients\s+)?~?\d+\+?\s*\w+\s+hours\s+\w+\b", re.IGNORECASE),
    re.compile(r"\b(?:restoring\s+100%\s+end-to-end\s+log\s+correlation|eliminating\s+DeadLetter\s+Queue\s+message\s+black\s+holes)\b", re.IGNORECASE),
    re.compile(r"\b(?:100%\s+graceful\s+failover|zero\s+ledger\s+corruption|zero\s+production\s+regressions?|zero\s+field-reported\s+recurrences?|zero\s+divergence)\b", re.IGNORECASE),
    re.compile(r"\b(?:47\s+production\s+rule\s+changes|10\+\s+operational\s+hours\s+weekly|sub-15\s+minutes|reduce\s+error\s+rates\s+to\s+near\s+zero)\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?%(?!\w)"),
]


class SurgicalOptimizer:
    """Surgically injects bold tags for ATS impact metrics and applies targeted delta patches."""

    def __init__(
        self,
        bold_cap: float = 0.15,
        max_bold_phrases: int = 2,
        allow_first_word_bold: bool = False,
        tag_type: str = "html",  # 'html' for <b>...</b> or 'markdown' for **...**
        bold_impact_only: bool = True,
        allow_jd_tech_bold: bool = True,
        allow_anchor_bold: bool = False,
        anchor_bold_words: int = 3,
    ) -> None:
        self.bold_cap = bold_cap
        self.max_bold_phrases = max_bold_phrases
        self.allow_first_word_bold = allow_first_word_bold
        self.tag_type = tag_type
        self.bold_impact_only = bold_impact_only
        self.allow_jd_tech_bold = allow_jd_tech_bold
        self.allow_anchor_bold = allow_anchor_bold
        self.anchor_bold_words = max(3, min(5, anchor_bold_words))

    def calculate_bold_ratio(self, text: str) -> float:
        """Calculate the proportion of bolded characters relative to total visible characters."""
        if not text:
            return 0.0

        bold_phrases = self.extract_bold_phrases(text)
        bold_chars = sum(len(p) for p in bold_phrases)

        visible_text = re.sub(r"</?[bi]>", "", text)
        visible_text = re.sub(r"\*\*|\*", "", visible_text)
        total_len = max(len(visible_text.strip()), 1)

        return bold_chars / total_len

    def extract_bold_phrases(self, text: str) -> List[str]:
        """Extract all bold text snippets from HTML <b> and Markdown ** tags."""
        if not text:
            return []
        html_bolds = re.findall(r"<b>(.*?)</b>", text, flags=re.IGNORECASE)
        md_bolds = re.findall(r"\*\*(.*?)\*\*", text)
        return html_bolds + md_bolds

    def _can_bold(self, matched_len: int, current_bold_chars: int, total_chars: int) -> bool:
        """Check if adding matched_len characters exceeds the bold character cap.

        Target: bold_cap (0.15). Tolerance: +0.10 to allow short metrics alongside tech terms.
        Effective ceiling: 0.25.
        """
        new_ratio = (current_bold_chars + matched_len) / max(total_chars, 1)
        return new_ratio <= (self.bold_cap + 0.10)

    def strip_tech_and_verb_bolds(self, text: str) -> str:
        """Strip bold tags from technologies, programming languages, frameworks, and action verbs."""
        if not text:
            return ""

        def _clean_match(m: re.Match) -> str:
            inner = m.group(1).strip()
            upper_inner = inner.upper()
            if upper_inner in STRONG_ACTION_VERBS or _is_known_tech(inner):
                return inner
            # Check if inner is pure tech combo like "Angular 18, .NET 6/8, and DynamoDB"
            for tech in _TECH_TERMS_UPPER:
                if len(tech) >= 3 and (tech in upper_inner or upper_inner in tech):
                    # If it doesn't contain a percentage or number/metric, it's technology
                    if not re.search(r"\d+%", inner) and not re.search(r"<\d+|sub-\d+|\$\d+", inner):
                        return inner
            return m.group(0)

        cleaned = re.sub(r"\*\*([^*]+?)\*\*", _clean_match, text)
        cleaned = re.sub(r"<b>([^<]+?)</b>", _clean_match, cleaned, flags=re.IGNORECASE)
        return cleaned

    def inject_bold_tags(self, bullet: str, keywords: Optional[List[str]] = None, impact_phrases: Optional[List[str]] = None) -> str:
        """Inject bold tags with priority: impact metrics > JD-matching tech > anchor (opt-in).

        Bolding rule: minimal, substance-first. Max 2 phrases, <=15% of bullet chars.
        """
        if not bullet:
            return ""

        text = clean_text_dashes(bullet)

        # Phase 1: Strip pre-existing bold tags to cleanly recalculate
        if self.bold_impact_only:
            text = re.sub(r"</?[bi]>|\*\*|\*", "", text)
        else:
            text = self.strip_tech_and_verb_bolds(text)

        # Phase 2: Strip leading action verb bold (unless anchor bold or first-word bold enabled)
        if not self.allow_first_word_bold and not self.allow_anchor_bold:
            text = re.sub(r"^\s*<b>([A-Za-z0-9\-\s/]+?)</b>(\s+)", r"\1\2", text, flags=re.IGNORECASE)
            text = re.sub(r"^\s*\*\*([A-Za-z0-9\-\s/]+?)\*\*(\s+)", r"\1\2", text)

        open_tag = "<b>" if self.tag_type == "html" else "**"
        close_tag = "</b>" if self.tag_type == "html" else "**"

        existing_bolds = self.extract_bold_phrases(text)
        current_bold_chars = sum(len(b) for b in existing_bolds)
        visible_text = re.sub(r"</?[bi]>|\*\*|\*", "", text)
        total_chars = max(len(visible_text), 1)
        bold_count = len(existing_bolds)

        # Phase 3a: Impact phrases (HIGHEST priority)
        impact_targets: List[str] = []
        if impact_phrases:
            impact_targets.extend(impact_phrases)

        for pat in IMPACT_PATTERNS:
            for match in pat.finditer(visible_text):
                phrase = match.group(0).strip()
                if phrase and phrase not in impact_targets and len(phrase) >= 3:
                    impact_targets.append(phrase)

        # Phase 3b: JD-matching tech terms (if allow_jd_tech_bold)
        tech_targets: List[str] = []
        if self.allow_jd_tech_bold and keywords:
            for kw in keywords:
                kw_clean = kw.strip()
                if not kw_clean or len(kw_clean) < 2:
                    continue
                if kw_clean.upper() in {t.upper() for t in impact_targets}:
                    continue
                # Check if this keyword actually appears in the bullet text
                kw_pattern = re.compile(rf"(?<!\w)({re.escape(kw_clean)})(?!\w)", re.IGNORECASE)
                if kw_pattern.search(visible_text):
                    tech_targets.append(kw_clean)

        # Phase 3c: Non-impact keywords (only when not bold_impact_only)
        keyword_targets: List[str] = []
        if not self.bold_impact_only and keywords:
            for kw in keywords:
                kw_clean = kw.strip()
                if not kw_clean or len(kw_clean) < 2:
                    continue
                if not _is_known_tech(kw_clean) and kw_clean not in impact_targets and kw_clean not in tech_targets:
                    keyword_targets.append(kw_clean)

        # Sort each priority group by length descending
        impact_targets.sort(key=len, reverse=True)
        tech_targets.sort(key=len, reverse=True)
        keyword_targets.sort(key=len, reverse=True)

        impact_bolds_applied = 0

        def _apply_targets(targets_list: List[str], text: str, current_bold_chars: int, bold_count: int, allow_tech: bool) -> tuple:
            """Apply a list of targets to text. Returns (text, current_bold_chars, bold_count, applied_count)."""
            applied = 0
            for target in targets_list:
                t_clean = target.strip()
                if not t_clean or len(t_clean) < 2:
                    continue
                if bold_count >= self.max_bold_phrases:
                    break
                if (current_bold_chars / total_chars) >= (self.bold_cap + 0.10):
                    break

                # Use (?<!\w)..(?!\w) instead of \b..\b — works for targets ending in %
                escaped_target = re.escape(t_clean)
                pattern = re.compile(
                    rf"(?<!<b>)(?<!\*\*)(?<!\w)({escaped_target})(?!\w)(?!</b>)(?!\*\*)",
                    re.IGNORECASE
                )
                match = pattern.search(text)
                if match:
                    matched_str = match.group(1)
                    # Block tech terms unless explicitly allowed (JD-matching or allow_jd_tech_bold)
                    if _is_known_tech(matched_str) and not allow_tech:
                        continue
                    if self._can_bold(len(matched_str), current_bold_chars, total_chars):
                        text = pattern.sub(f"{open_tag}\\1{close_tag}", text, count=1)
                        current_bold_chars += len(matched_str)
                        bold_count += 1
                        applied += 1
            return text, current_bold_chars, bold_count, applied

        # Phase 4a: Apply impact targets first (always allowed)
        text, current_bold_chars, bold_count, impact_applied = _apply_targets(
            impact_targets, text, current_bold_chars, bold_count, allow_tech=True
        )
        impact_bolds_applied = impact_applied

        # Phase 4b: Apply JD-matching tech targets (tech allowed)
        text, current_bold_chars, bold_count, _ = _apply_targets(
            tech_targets, text, current_bold_chars, bold_count, allow_tech=True
        )

        # Phase 4c: Apply non-tech keyword targets (tech blocked)
        if keyword_targets:
            text, current_bold_chars, bold_count, _ = _apply_targets(
                keyword_targets, text, current_bold_chars, bold_count, allow_tech=False
            )

        # Phase 5: Anchor bold — first N words as single phrase (opt-in, only if no impact metrics bolded)
        if self.allow_anchor_bold and impact_bolds_applied == 0 and bold_count < self.max_bold_phrases:
            text = self._apply_anchor_bold(text, open_tag, close_tag, current_bold_chars, total_chars, bold_count)

        return text

    def _apply_anchor_bold(
        self, text: str, open_tag: str, close_tag: str,
        current_bold_chars: int, total_chars: int, bold_count: int
    ) -> str:
        """Bold the first `anchor_bold_words` words of the bullet as a single phrase."""
        # Strip bullet marker prefix
        stripped = re.sub(r"^[\*\-•>\s]+", "", text).strip()
        if not stripped:
            return text

        words = stripped.split()
        n = min(self.anchor_bold_words, len(words))
        if n < 2:
            return text

        anchor_phrase = " ".join(words[:n])
        anchor_len = len(anchor_phrase)

        # Anchor is a single prominent phrase — allow up to bold_cap + 0.25 (40% effective)
        anchor_ratio = (current_bold_chars + anchor_len) / max(total_chars, 1)
        if anchor_ratio > (self.bold_cap + 0.25):
            return text

        # Escape regex special chars in anchor phrase
        escaped = re.escape(anchor_phrase)
        pattern = re.compile(rf"(?<!<b>)(?<!\*\*)({escaped})(?!</b>)(?!\*\*)", re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(f"{open_tag}\\1{close_tag}", text, count=1)
        return text

    def optimize_bullets(self, bullets: List[str], keywords: Optional[List[str]] = None, impact_phrases: Optional[List[str]] = None) -> List[str]:
        """Process a list of bullet points, injecting ATS impact bold tags."""
        return [self.inject_bold_tags(b, keywords, impact_phrases) for b in bullets]

    def apply_patches(
        self, bullets: List[str], critiques: List[Dict[str, Any]]
    ) -> List[str]:
        """Apply targeted critique patches and deduplicate leading action verbs via micro-linter."""
        patched = list(bullets)

        # 1. Apply suggested patches from critiques
        for critique in critiques:
            idx = critique.get("bullet_index")
            if idx is not None and 0 <= idx < len(patched):
                if "suggested_patch" in critique:
                    patched[idx] = critique["suggested_patch"]

        # 2. Deterministic micro-linter: deduplicate leading action verbs
        seen_verbs: Set[str] = set()
        for i, bullet in enumerate(patched):
            clean_b = bullet.lstrip("*- •>").strip()
            words = clean_b.split()
            if not words:
                continue

            verb = words[0]
            # Match casing variation if needed
            verb_title = verb.capitalize()

            if verb_title in seen_verbs:
                # Find the first unused alternative
                alternatives = ACTION_VERB_ALTERNATIVES.get(verb_title, [])
                replacement = None
                for alt in alternatives:
                    if alt not in seen_verbs:
                        replacement = alt
                        break
                if replacement:
                    words[0] = replacement
                    # Preserve any leading bullet marker if originally present
                    prefix = bullet[: len(bullet) - len(clean_b)]
                    patched[i] = prefix + " ".join(words)
                    seen_verbs.add(replacement)
                else:
                    seen_verbs.add(verb_title)
            else:
                seen_verbs.add(verb_title)

        return patched
