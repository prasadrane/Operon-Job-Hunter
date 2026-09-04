"""Email Status Classifier with Inverted Precedence Hierarchy."""

import re
from typing import Optional


class StatusClassifier:
    """Classifies incoming recruiting emails into standardized lifecycle statuses.

    Uses an inverted precedence hierarchy where rejection signals take absolute precedence
    over interview and assessment keywords to prevent false positives (e.g. post-interview
    rejections containing 'interview' or 'assessment' in the preamble).
    """

    REJECTION_PATTERNS = [
        r"\bunfortunately\b",
        r"\b(?:will\s+not|not)\s+be\s+moving\s+forward\b",
        r"\bdecided\s+not\s+to\s+(?:proceed|move\s+forward)\b",
        r"\b(?:pursuing|pursue|with)\s+other\s+candidates?\b",
        r"\b(?:pursuing|pursue|with)\s+another\s+candidate\b",
        r"\bunable\s+to\s+(?:offer|extend\s+an?\s+offer|proceed)\b",
        r"\bcannot\s+offer\b",
        r"\bnot\s+selected\b",
        r"\bregret\s+to\s+inform\b",
        r"\bdecided\s+to\s+pursue\s+other\b",
        r"\bdecided\s+to\s+move\s+forward\s+with\s+other\b",
        r"\bposition\s+has\s+been\s+filled\b",
        r"\brole\s+has\s+been\s+(?:filled|closed)\b",
        r"\bnot\s+a\s+match\b",
        r"\bnot\s+matching\b",
        r"\bnot\s+moving\s+ahead\b",
        r"\bwill\s+not\s+be\s+able\s+to\s+offer\b",
        r"\bwon'?t\s+be\s+moving\s+forward\b",
        r"很遗憾",
        r"暂不匹配",
        r"不合适",
        r"未能进入下一轮",
        r"未通过",
        r"不再考虑",
        r"决定不推进",
    ]

    OA_PATTERNS = [
        r"\bhackerrank\b",
        r"\bcodesignal\b",
        r"\bonline\s+assessment\b",
        r"\bcoding\s+challenge\b",
        r"\btake-?home\s+assessment\b",
        r"\btechnical\s+assessment\b",
        r"\btimed\s+assessment\b",
        r"\bcoding\s+test\b",
        r"\bcomplete\s+(?:an?\s+)?assessment\b",
        r"\bassessment\s+from\b",
        r"完成测评",
        r"在线测评",
        r"笔试题",
    ]

    INTERVIEW_PATTERNS = [
        r"\binterview\b",
        r"\btechnical\s+screen\b",
        r"\bphone\s+screen\b",
        r"\bspeak\s+with\b",
        r"\bchat\s+with\s+the\s+team\b",
        r"\bmeet\s+the\s+team\b",
        r"\bschedule\s+(?:an?|your)\s+interview\b",
        r"\bscheduling\s+link\b",
        r"\bvideo\s+interview\b",
        r"\bscreening\s+call\b",
        r"\bfirst\s+round\s+interview\b",
        r"\bonsite\s+interview\b",
        r"\bfinal\s+round\b",
        r"\binterview\s+invitation\b",
        r"\binvite\s+you\s+to\s+interview\b",
        r"邀您面试",
        r"邀约面试",
        r"安排面试",
        r"预约面试",
        r"面试邀请",
    ]

    def classify(self, email_body: str, subject: str = "", sender: str = "") -> str:
        """Classify an email's content using inverted precedence hierarchy.

        Hierarchy order:
        1. REJECTED: checked first so rejections like 'Thank you for interviewing... unfortunately'
           are never misclassified as interviews.
        2. OA_INVITE: checked second for coding/assessment invitations.
        3. INTERVIEW_INVITE: checked third for live screens and team interviews.
        4. STATUS_UPDATE: fallback for submission confirmations, status updates, or other touches.
        """
        text = f"{sender} {subject} {email_body}".strip()

        # 1. Inverted precedence: check rejection first
        for pat in self.REJECTION_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return "REJECTED"

        # 2. Check OA / assessment invitations
        for pat in self.OA_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return "OA_INVITE"

        # 3. Check Interview invitations
        for pat in self.INTERVIEW_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return "INTERVIEW_INVITE"

        # 4. Fallback status update
        return "STATUS_UPDATE"
