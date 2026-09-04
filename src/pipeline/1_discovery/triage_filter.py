"""
Stage 0 Fast-Reject Triage Filter.

TF-IDF + logistic regression classifier for rapid job relevance scoring.
VIP watchlist bypass, 5% audit queue, auto-decay on FNR > 0.5%.
"""

import json
import logging
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def _companies_yaml_path() -> Path:
    from src.core.config import get_settings
    return get_settings().companies_yaml_path


_DECAY_STEP = 0.03
_DECAY_MIN = 0.05
_FNR_THRESHOLD = 0.005  # 0.5%
_COOLDOWN_HOURS = 6
_AUDIT_SAMPLE_RATE = 0.05

# ---------------------------------------------------------------------------
# Synthetic training corpus (in-memory, no disk I/O)
# ---------------------------------------------------------------------------
# Minimal seed corpus for the TF-IDF + SGD classifier.  In production this
# would be a labelled dataset; here we use rule-of-thumb keywords so the
# model is deterministic and test-friendly without external files.

_RELEVANT_DOCS = [
    "senior software engineer python distributed systems microservices",
    "backend developer go kubernetes docker CI/CD AWS cloud infrastructure",
    "machine learning engineer pytorch tensorflow deep learning neural networks",
    "full stack developer react typescript node.js REST API GraphQL",
    "data scientist pandas scikit-learn statistics regression classification",
    "devops engineer terraform ansible jenkins monitoring observability",
    "platform engineer linux networking reliability SRE incident response",
    "security engineer penetration testing vulnerability assessment compliance",
    "staff engineer architecture design review mentoring technical leadership",
    "principal engineer system design scalability performance optimization",
]

_IRRELEVANT_DOCS = [
    "retail associate customer service cash register inventory stocking",
    "restaurant waiter server food preparation dishwashing tips",
    "delivery driver license vehicle packages route navigation",
    "graphic designer photoshop illustrator branding typography layout",
    "administrative assistant filing scheduling email correspondence",
    "construction worker heavy lifting building materials safety equipment",
    "nursing assistant patient care vital signs hygiene medication",
    "real estate agent property listings showings negotiations commissions",
    "make coffee fetch lunch orders errands personal assistant tasks",
    "social media influencer content creation followers engagement",
]

# ---------------------------------------------------------------------------
# VIP Watchlist
# ---------------------------------------------------------------------------

_VIP_COMPANIES: set[str] = set()


def _load_vip_watchlist() -> set[str]:
    """Load company names from companies.yaml as VIP watchlist."""
    global _VIP_COMPANIES
    if _VIP_COMPANIES:
        return _VIP_COMPANIES
    yaml_path = _companies_yaml_path()
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for company in data.get("companies", []):
            name = company.get("name", "")
            if name:
                _VIP_COMPANIES.add(name.lower())
    except FileNotFoundError:
        logger.warning("companies.yaml not found at %s — VIP watchlist empty", yaml_path)
    return _VIP_COMPANIES


def is_vip_bypass(company: str) -> bool:
    """Check if company is on VIP watchlist (case-insensitive)."""
    if not company:
        return False
    watchlist = _load_vip_watchlist()
    return company.strip().lower() in watchlist


# ---------------------------------------------------------------------------
# Notification helpers (no-ops if services unavailable)
# ---------------------------------------------------------------------------

def _dispatch_telegram_alert(message: str) -> None:
    """Dispatch Telegram alert — best-effort, no-op if token missing."""
    try:
        from src.core.config import get_settings
        settings = get_settings()
        if not getattr(settings, "TELEGRAM_BOT_TOKEN", None):
            return
        import urllib.request
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        data = json.dumps({
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": message,
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.debug("Telegram alert failed (non-fatal): %s", e)


def _emit_sse_event(event_type: str, data: dict) -> None:
    """Emit SSE event — best-effort, no-op if event bus unavailable."""
    try:
        from src.interface.api import sse_bus  # type: ignore[import-not-found]
        sse_bus.emit(event_type, data)
    except Exception:
        logger.debug("SSE emit for %s skipped (bus unavailable)", event_type)


# ---------------------------------------------------------------------------
# TriageFilter
# ---------------------------------------------------------------------------

class TriageFilter:
    """Stage 0 fast-reject triage filter.

    Parameters
    ----------
    threshold : float
        Initial score threshold τ (default 0.15).  Scores below τ → "drop",
        τ ≤ score < 0.40 → "flag", score ≥ 0.40 → "pass".
    """

    def __init__(self, threshold: float = 0.15):
        self.threshold = threshold
        self._last_decay_time: Optional[datetime] = None

        # Build TF-IDF + SGD model in-memory
        self.tfidf = TfidfVectorizer(max_features=5000, stop_words="english")
        self.clf = SGDClassifier(loss="log_loss", max_iter=200, random_state=42)

        all_docs = _RELEVANT_DOCS + _IRRELEVANT_DOCS
        labels = np.array([1] * len(_RELEVANT_DOCS) + [0] * len(_IRRELEVANT_DOCS))
        X = self.tfidf.fit_transform(all_docs)
        self.clf.fit(X, labels)

    # ------------------------------------------------------------------
    # Internal scoring
    # ------------------------------------------------------------------

    def _score(self, job_description: str) -> float:
        """Return relevance probability in [0, 1]."""
        X = self.tfidf.transform([job_description])
        proba = self.clf.predict_proba(X)[0]
        # predict_proba returns [P(neg), P(pos)]; we want P(pos)
        pos_idx = list(self.clf.classes_).index(1) if 1 in self.clf.classes_ else -1
        return float(proba[pos_idx]) if pos_idx >= 0 else 0.0

    def _should_audit_sample(self) -> bool:
        """Probabilistic 5% sampling gate."""
        return random.random() < _AUDIT_SAMPLE_RATE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        job_description: str,
        company: Optional[str] = None,
    ) -> tuple[float, str]:
        """Score a job description and return (score, decision).

        Decision mapping:
        - VIP bypass → "pass" regardless of score
        - score < τ   → "drop"
        - τ ≤ score < 0.40 → "flag"
        - score ≥ 0.40 → "pass"
        """
        if company and is_vip_bypass(company):
            return (1.0, "pass")

        score = self._score(job_description)

        if score < self.threshold:
            decision = "drop"
        elif score < 0.40:
            decision = "flag"
        else:
            decision = "pass"

        return (score, decision)

    def log_audit_sample(
        self,
        job: dict,
        score: float,
        path: Optional[str] = None,
    ) -> None:
        """Log a dropped job to the audit queue (5% sample)."""
        audit_path = Path(path) if path else (_PROJECT_ROOT / "data" / "triage_audit.jsonl")
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "job_id": job.get("job_id", ""),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "score": score,
            "timestamp": datetime.utcnow().isoformat(),
        }
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def update_threshold(self, new_fnr: float) -> None:
        """Auto-decay τ by 0.03 when FNR > 0.5%, with 6h cooldown.

        Floor at 0.05.  Dispatches Telegram alert + SSE event on decay.
        """
        if new_fnr <= _FNR_THRESHOLD:
            return

        now = datetime.utcnow()
        if self._last_decay_time is not None:
            if (now - self._last_decay_time) < timedelta(hours=_COOLDOWN_HOURS):
                logger.debug("Decay suppressed — cooldown active")
                return

        old = self.threshold
        self.threshold = max(_DECAY_MIN, round(self.threshold - _DECAY_STEP, 4))
        self._last_decay_time = now

        msg = f"triage_decay: τ {old:.2f} → {self.threshold:.2f} (FNR={new_fnr:.4f})"
        logger.info(msg)
        _dispatch_telegram_alert(msg)
        _emit_sse_event("alert_triage_decay_triggered", {
            "old_threshold": old,
            "new_threshold": self.threshold,
            "fnr": new_fnr,
        })
