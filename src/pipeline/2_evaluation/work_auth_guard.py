"""Work Authorization & Hard Visa Blocker Guard for CareerGraph AI."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
import json
from pydantic import BaseModel, Field


class WorkAuthResult(BaseModel):
    """Result of Work Authorization evaluation."""

    has_blocker: bool = False
    reasons: List[str] = Field(default_factory=list)
    matched_phrases: List[str] = Field(default_factory=list)
    confidence_score: float = 1.0
    consensus_votes: Optional[Dict[str, Any]] = None


class WorkAuthGuard:
    """Evaluates job descriptions for hard visa sponsorship and citizenship blockers."""

    # Explicit positive signals to avoid false positives
    POSITIVE_SPONSORSHIP_PATTERNS = [
        re.compile(r"\bwe (do )?sponsor\b", re.IGNORECASE),
        re.compile(r"\b(visa )?sponsorship is available\b", re.IGNORECASE),
        re.compile(r"\b(visa )?sponsorship provided\b", re.IGNORECASE),
        re.compile(r"\bopen to (visa )?sponsorship\b", re.IGNORECASE),
        re.compile(r"\b(h-?1b|greencard|green card) (sponsorship|transfers?)\b", re.IGNORECASE),
    ]

    # Hard blocker regex patterns
    BLOCKER_PATTERNS = [
        # 1. US Citizen Only / Citizenship required
        (
            re.compile(
                r"\b(must be (a )?(u\.?s\.?|united states) citizen|"
                r"u\.?s\.? citizens? only|"
                r"united states citizens? only|"
                r"citizenship required|"
                r"u\.?s\.? citizenship is required|"
                r"only (u\.?s\.?|united states) citizens?|"
                r"open to (u\.?s\.?|united states) citizens? only)\b",
                re.IGNORECASE,
            ),
            "Job requires US Citizenship only.",
        ),
        # 2. Citizen or Permanent Resident / Green Card only (no visa candidates)
        (
            re.compile(
                r"\b((u\.?s\.?|united states) citizens? or (green card|permanent resident) holders? only|"
                r"citizens? or permanent residents? only|"
                r"must be a (u\.?s\.?|united states) citizen or (green card|permanent resident)|"
                r"(green card|permanent resident) or (u\.?s\.?|united states) citizen only)\b",
                re.IGNORECASE,
            ),
            "Job restricted to US Citizens or Permanent Residents only.",
        ),
        # 3. Explicit No Sponsorship statements
        (
            re.compile(
                r"\b(no (visa )?sponsorship( (is )?provided)?( (now|currently) or in the future)?|"
                r"will not (provide |offer )?(visa )?sponsor(ship)?|"
                r"cannot (provide |offer )?(visa )?sponsor(ship)?|"
                r"unable to (provide |offer )?(visa )?sponsor(ship)?|"
                r"not (able to|offering|providing) (visa )?sponsorship|"
                r"without (visa )?sponsorship|"
                r"no current or future (visa )?sponsorship|"
                r"(visa )?sponsorship is not (available|offered|provided)|"
                r"no (visa )?sponsorship of any kind|"
                r"(visa )?sponsorship not supported|"
                r"does not (offer|provide) (visa )?sponsorship)\b",
                re.IGNORECASE,
            ),
            "Employer explicitly does not provide visa sponsorship.",
        ),
        # 4. Security Clearance requirements
        (
            re.compile(
                r"\b(top secret|ts/sci|active secret clearance|"
                r"security clearance required|"
                r"must (possess|hold|obtain|have) (an? )?(active )?(top secret|secret|security) clearance|"
                r"must be clearable|dod clearance required)\b",
                re.IGNORECASE,
            ),
            "Role requires active Security Clearance / DOD clearance.",
        ),
        # 5. ITAR / Export Control strict citizenship clauses
        (
            re.compile(
                r"\b(itar compliance|itar requirements?|"
                r"export control regulations require (u\.?s\.?|united states) citizenship)\b",
                re.IGNORECASE,
            ),
            "ITAR / Export Control restricts role to US Persons/Citizens.",
        ),
    ]

    def check(self, jd_text: str) -> WorkAuthResult:
        """Check if job description contains any hard work authorization blockers."""
        if not jd_text or not jd_text.strip():
            return WorkAuthResult(has_blocker=False, confidence_score=1.0)

        text = jd_text.strip()
        reasons: List[str] = []
        matched: List[str] = []

        for pattern, description in self.BLOCKER_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_phrase = match.group(0)
                reasons.append(f"{description} (Matched: '{matched_phrase}')")
                matched.append(matched_phrase)

        has_blocker = len(reasons) > 0
        return WorkAuthResult(
            has_blocker=has_blocker,
            reasons=reasons,
            matched_phrases=matched,
            confidence_score=0.95 if has_blocker else 0.90,
            consensus_votes={"rule_vote": has_blocker},
        )

    def evaluate_consensus(self, jd_text: str, llm: Any = None) -> WorkAuthResult:
        """Evaluate work authorization using multi-model consensus voting."""
        rule_result = self.check(jd_text)
        if not llm:
            return rule_result

        prompt = (
            "You are a strict Work Authorization compliance classifier.\n"
            "Analyze the following job description text and determine whether it contains a HARD BLOCKER "
            "for visa holders (e.g. US Citizen only, active Security Clearance, no sponsorship now or in the future).\n\n"
            f"Job Description:\n\"\"\"\n{jd_text[:3000]}\n\"\"\"\n\n"
            "Return JSON matching this schema:\n"
            "{\n"
            "  \"has_blocker\": true | false,\n"
            "  \"confidence\": 0.0 - 1.0,\n"
            "  \"reason\": \"brief explanation\"\n"
            "}"
        )

        try:
            raw = llm.generate(prompt)
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            parsed = json.loads(raw)
            llm_vote = bool(parsed.get("has_blocker", False))
            llm_conf = float(parsed.get("confidence", 0.85))
            llm_reason = str(parsed.get("reason", ""))

            # Consensus aggregation
            votes = {
                "rule_vote": rule_result.has_blocker,
                "llm_vote": llm_vote,
                "llm_confidence": llm_conf,
            }

            # If rule has a hard blocker (US Citizen / TS SCI), rule + LLM consensus
            if rule_result.has_blocker and llm_vote:
                final_blocker = True
                conf = max(rule_result.confidence_score, llm_conf)
                reasons = rule_result.reasons + [f"LLM Consensus: {llm_reason}"]
            elif not rule_result.has_blocker and not llm_vote:
                final_blocker = False
                conf = max(rule_result.confidence_score, llm_conf)
                reasons = []
            elif llm_vote and not rule_result.has_blocker:
                # LLM caught a nuanced blocker not in regex
                final_blocker = True
                conf = llm_conf
                reasons = [f"LLM Visa Guard: {llm_reason}"]
            else:
                # Rule flagged, but LLM disambiguated (e.g. positive exception)
                final_blocker = False if llm_conf >= 0.85 else rule_result.has_blocker
                conf = llm_conf
                reasons = [f"Disambiguated by LLM: {llm_reason}"] if not final_blocker else rule_result.reasons

            return WorkAuthResult(
                has_blocker=final_blocker,
                reasons=reasons,
                matched_phrases=rule_result.matched_phrases,
                confidence_score=conf,
                consensus_votes=votes,
            )
        except Exception:
            # Fallback gracefully to rule result on LLM error
            return rule_result

    def has_blocker(self, jd_text: str) -> bool:
        """Convenience method returning boolean blocker status."""
        return self.check(jd_text).has_blocker

