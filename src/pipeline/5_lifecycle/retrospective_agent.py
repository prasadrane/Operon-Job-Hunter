"""Retrospective Agent: Ingests session telemetry, computes performance metrics, and extracts learned ATS quirks."""

from dataclasses import asdict, dataclass, field
import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

from src.core.memory.core_memory_manager import CoreMemoryManager

logger = logging.getLogger(__name__)


@dataclass
class SessionMetrics:
    total_submissions: int = 0
    successful_submissions: int = 0
    precision_score: float = 0.0
    efficiency_score: float = 0.0
    healing_events_count: int = 0
    avg_latency_s: float = 0.0
    total_tokens: int = 0


class RetrospectiveAgent:
    """Post-session self-learning agent analyzing telemetry traces and compiling learned ATS quirks."""

    def __init__(
        self,
        telemetry_path: str = "./data/telemetry.db",
        quirks_path: str = "./data/ats_quirks.json",
        core_memory: Optional[CoreMemoryManager] = None,
    ) -> None:
        self.telemetry_path = telemetry_path
        self.quirks_path = quirks_path
        self.core_memory = core_memory or CoreMemoryManager(sync_db=False)
        os.makedirs(os.path.dirname(os.path.abspath(self.quirks_path)), exist_ok=True)

    def load_audit_spans(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Query audit spans from SQLite telemetry database."""
        if not os.path.exists(self.telemetry_path):
            return []

        spans: List[Dict[str, Any]] = []
        try:
            with sqlite3.connect(self.telemetry_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT span_id, event, tokens, metadata, created_at
                    FROM audit_spans
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    (limit,),
                )
                for row in cursor.fetchall():
                    span_id, event, tokens, metadata_str, created_at = row
                    meta = {}
                    if metadata_str:
                        try:
                            meta = json.loads(metadata_str)
                        except Exception:
                            meta = {"raw": metadata_str}
                    spans.append({
                        "span_id": span_id,
                        "event": event,
                        "tokens": tokens or 0,
                        "metadata": meta,
                        "created_at": created_at,
                    })
        except Exception as e:
            logger.error("Failed to load audit spans from %s: %s", self.telemetry_path, e)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="lifecycle",
                    component="retrospective_agent",
                    error_type="TELEMETRY_READ_ERROR",
                    message=f"Failed to load audit spans from {self.telemetry_path}: {e}",
                    metadata={"telemetry_path": self.telemetry_path},
                )
            except Exception:
                pass

        return spans

    def compute_session_metrics(self) -> SessionMetrics:
        """Analyze spans and compute session performance rubric."""
        spans = self.load_audit_spans()
        metrics = SessionMetrics()

        sub_success = 0
        sub_total = 0
        healing_count = 0
        latencies: List[float] = []
        tokens = 0

        for s in spans:
            tokens += s.get("tokens", 0)
            event = s.get("event", "")
            meta = s.get("metadata", {})

            if "form_submission" in event or "submission" in event:
                sub_total += 1
                if meta.get("success", False) or "success" in event:
                    sub_success += 1
                if "latency_s" in meta:
                    latencies.append(float(meta["latency_s"]))

            elif event == "form_healing_event":
                healing_count += 1

        metrics.total_submissions = sub_total
        metrics.successful_submissions = sub_success
        metrics.total_tokens = tokens
        metrics.healing_events_count = healing_count
        metrics.precision_score = round((sub_success / sub_total * 100.0), 2) if sub_total > 0 else 100.0
        metrics.avg_latency_s = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        # Efficiency is inversely proportional to excessive latency and fallbacks (scaled 0-100)
        metrics.efficiency_score = max(0.0, round(100.0 - (metrics.avg_latency_s * 2.0), 2))

        return metrics

    def extract_and_persist_quirks(self, max_age_days: int = 30) -> Dict[str, Any]:
        """Extract learned selectors from healing event spans and persist to data/ats_quirks.json."""
        spans = self.load_audit_spans()
        existing_quirks: Dict[str, Any] = {}
        now_ts = time.time()
        max_age_sec = max_age_days * 86400

        if os.path.exists(self.quirks_path):
            try:
                with open(self.quirks_path, "r", encoding="utf-8") as f:
                    existing_quirks = json.load(f)
            except Exception:
                existing_quirks = {}

        for s in spans:
            if s.get("event") == "form_healing_event":
                meta = s.get("metadata", {})
                company = meta.get("company", "Generic")
                field_name = meta.get("field_name")
                healed_sel = meta.get("healed_selector")
                portal_type = meta.get("portal_type", "unknown")
                domain = meta.get("domain", "")
                ts = float(meta.get("timestamp", now_ts))

                # Check TTL expiration
                if (now_ts - ts) > max_age_sec:
                    continue

                if company and field_name and healed_sel:
                    if company not in existing_quirks:
                        existing_quirks[company] = {}
                    existing_quirks[company][field_name] = {
                        "portal_type": portal_type,
                        "domain": domain,
                        "healed_selector": healed_sel,
                        "original_selector": meta.get("original_selector", ""),
                        "action": meta.get("action", ""),
                        "updated_at": ts,
                    }

        try:
            with open(self.quirks_path, "w", encoding="utf-8") as f:
                json.dump(existing_quirks, f, indent=2)
            logger.info("Persisted %d learned company quirks to %s", len(existing_quirks), self.quirks_path)
        except Exception as e:
            logger.error("Failed to write learned quirks to %s: %s", self.quirks_path, e)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="lifecycle",
                    component="retrospective_agent",
                    error_type="PERSIST_ERROR",
                    message=f"Failed to write learned quirks to {self.quirks_path}: {e}",
                    metadata={"quirks_path": self.quirks_path},
                )
            except Exception:
                pass

        return existing_quirks

    def generate_retrospective_digest(self) -> str:
        """Produce human-readable Markdown retrospective digest."""
        metrics = self.compute_session_metrics()
        quirks = self.extract_and_persist_quirks()

        lines = [
            "# Session Retrospective & Self-Learning Digest",
            "",
            "### 1. Performance Rubric",
            f"- **Precision Score:** {metrics.precision_score}% ({metrics.successful_submissions}/{metrics.total_submissions} applications)",
            f"- **Efficiency Score:** {metrics.efficiency_score}/100",
            f"- **Average Step Latency:** {metrics.avg_latency_s}s",
            f"- **Self-Healing Interventions:** {metrics.healing_events_count} event(s) auto-resolved",
            f"- **Total Tokens Consumed:** {metrics.total_tokens}",
            "",
            "### 2. Learned ATS Quirks & Selector Fixes",
        ]

        if not quirks:
            lines.append("- *No new quirks recorded in this session.*")
        else:
            for company, fields in quirks.items():
                lines.append(f"- **{company}:**")
                for f_name, f_data in fields.items():
                    lines.append(f"  - `{f_name}` $\\rightarrow$ `{f_data.get('healed_selector')}` (*{f_data.get('action')}*)")

        lines.append("")
        lines.append("### 3. Core Memory Status")
        for k, v in self.core_memory.list_directives().items():
            lines.append(f"- **{k.upper()}:** {v}")

        return "\n".join(lines)

    def sync_insights_to_graph(self, company_insights: Optional[Dict[str, Any]] = None) -> int:
        """Sync discovered company ATS quirks and learnings into Core Memory & GraphRAG."""
        quirks = company_insights or self.extract_and_persist_quirks()
        count = 0
        for company, fields in quirks.items():
            for field_name, f_data in fields.items():
                directive_key = f"ats_quirk_{company.lower().replace(' ', '_')}_{field_name}"
                directive_val = f"{company} {field_name} uses {f_data.get('healed_selector')} ({f_data.get('action')})"
                self.core_memory.save_directive(directive_key, directive_val)
                count += 1
        return count
