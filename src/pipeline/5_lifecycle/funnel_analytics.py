"""Funnel Analytics & Conversion Metrics Calculator for CareerGraph AI."""

import statistics
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.core.db.repository import ApplicationRepository, JobRepository
from src.core.models import ApplicationRecord, JobPosting, JobStatus


class FunnelMetrics(BaseModel):
    """Aggregated lifecycle conversion metrics and ATS portal performance."""

    total_applied: int = 0
    total_active: int = 0
    total_acknowledged: int = 0
    total_interviewing: int = 0
    total_offers: int = 0
    total_rejections: int = 0
    total_ghost: int = 0
    interview_rate_pct: float = 0.0
    offer_rate_pct: float = 0.0
    rejection_rate_pct: float = 0.0
    avg_response_latency_days: float = 0.0
    median_response_latency_days: float = 0.0
    portal_breakdown: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    status_breakdown: Dict[str, int] = Field(default_factory=dict)
    summary_markdown: Optional[str] = None


class FunnelAnalytics:
    """Computes comprehensive application lifecycle analytics, latency metrics, and conversion rates."""

    def __init__(
        self,
        app_repo: Optional[ApplicationRepository] = None,
        job_repo: Optional[JobRepository] = None,
    ):
        self.app_repo = app_repo
        self.job_repo = job_repo

    def calculate_metrics(
        self,
        applications: Optional[List[ApplicationRecord]] = None,
        jobs: Optional[List[JobPosting]] = None,
    ) -> FunnelMetrics:
        """Compute full conversion funnel metrics from application and job records."""
        if applications is None and self.app_repo:
            applications = self.app_repo.list_applications()
        elif applications is None:
            applications = []

        job_map: Dict[str, JobPosting] = {}
        if jobs is not None:
            job_map = {j.id: j for j in jobs}
        elif self.job_repo:
            all_jobs = self.job_repo.get_all_jobs()
            job_map = {j.id: j for j in all_jobs}

        total_applied = len(applications)
        status_breakdown: Dict[str, int] = {}
        portal_stats: Dict[str, Dict[str, int]] = {}
        latencies: List[float] = []

        total_active = 0
        total_acknowledged = 0
        total_interviewing = 0
        total_offers = 0
        total_rejections = 0
        total_ghost = 0

        for app in applications:
            st = app.status.value.lower() if isinstance(app.status, JobStatus) else str(app.status).lower()
            status_breakdown[st] = status_breakdown.get(st, 0) + 1

            if st in ("applied", "acknowledged", "interviewing", "offer", "assessment"):
                total_active += 1

            if st in ("acknowledged", "confirmation"):
                total_acknowledged += 1
            elif st in ("interviewing", "interview"):
                total_interviewing += 1
            elif st == "offer":
                total_offers += 1
            elif st == "rejected":
                total_rejections += 1
            elif st in ("ghost_job", "ghost"):
                total_ghost += 1

            # Response latency calculation
            if app.last_status_update and app.applied_at:
                diff_seconds = (app.last_status_update - app.applied_at).total_seconds()
                latency_days = max(0.0, diff_seconds / 86400.0)
                latencies.append(round(latency_days, 2))

            # Portal resolution
            portal = "generic"
            if app.job_id in job_map:
                portal = job_map[app.job_id].portal_type or "generic"
            elif app.portal_url:
                url_lower = app.portal_url.lower()
                if "greenhouse.io" in url_lower:
                    portal = "greenhouse"
                elif "lever.co" in url_lower:
                    portal = "lever"
                elif "ashbyhq.com" in url_lower:
                    portal = "ashby"
                elif "myworkdayjobs.com" in url_lower or "workday" in url_lower:
                    portal = "workday"

            portal_entry = portal_stats.setdefault(
                portal,
                {"total": 0, "interviewing": 0, "offers": 0, "rejections": 0},
            )
            portal_entry["total"] += 1
            if st in ("interviewing", "interview"):
                portal_entry["interviewing"] += 1
            elif st == "offer":
                portal_entry["offers"] += 1
            elif st == "rejected":
                portal_entry["rejections"] += 1

        # Rates calculation
        interview_rate_pct = round((total_interviewing / total_applied) * 100.0, 2) if total_applied > 0 else 0.0
        offer_rate_pct = round((total_offers / total_applied) * 100.0, 2) if total_applied > 0 else 0.0
        rejection_rate_pct = round((total_rejections / total_applied) * 100.0, 2) if total_applied > 0 else 0.0

        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        median_latency = round(float(statistics.median(latencies)), 2) if latencies else 0.0

        # Formatted portal breakdown
        portal_breakdown: Dict[str, Dict[str, Any]] = {}
        for p_name, p_data in portal_stats.items():
            p_total = p_data["total"]
            p_conv = round(((p_data["interviewing"] + p_data["offers"]) / p_total) * 100.0, 2) if p_total > 0 else 0.0
            portal_breakdown[p_name] = {
                "total": p_total,
                "interviewing": p_data["interviewing"],
                "offers": p_data["offers"],
                "rejections": p_data["rejections"],
                "conversion_rate_pct": p_conv,
            }

        metrics = FunnelMetrics(
            total_applied=total_applied,
            total_active=total_active,
            total_acknowledged=total_acknowledged,
            total_interviewing=total_interviewing,
            total_offers=total_offers,
            total_rejections=total_rejections,
            total_ghost=total_ghost,
            interview_rate_pct=interview_rate_pct,
            offer_rate_pct=offer_rate_pct,
            rejection_rate_pct=rejection_rate_pct,
            avg_response_latency_days=avg_latency,
            median_response_latency_days=median_latency,
            portal_breakdown=portal_breakdown,
            status_breakdown=status_breakdown,
        )

        metrics.summary_markdown = self.generate_report_markdown(metrics)
        return metrics

    def generate_report_markdown(self, metrics: FunnelMetrics) -> str:
        """Format metrics into a clean markdown executive report."""
        lines = [
            "# Application Funnel & Lifecycle Analytics",
            "",
            "## Summary Metrics",
            f"- **Total Applied:** {metrics.total_applied}",
            f"- **Active In-Flight:** {metrics.total_active}",
            f"- **Interview Rate:** {metrics.interview_rate_pct:.1f}% ({metrics.total_interviewing} interviews)",
            f"- **Offer Rate:** {metrics.offer_rate_pct:.1f}% ({metrics.total_offers} offers)",
            f"- **Rejection Rate:** {metrics.rejection_rate_pct:.1f}% ({metrics.total_rejections} rejections)",
            f"- **Average Response Latency:** {metrics.avg_response_latency_days:.1f} days",
            f"- **Median Response Latency:** {metrics.median_response_latency_days:.1f} days",
            "",
            "## ATS Portal Performance",
            "| Portal | Applications | Interviews | Offers | Rejections | Conversion % |",
            "|:---|:---:|:---:|:---:|:---:|:---:|",
        ]

        if metrics.portal_breakdown:
            for portal, stats in sorted(metrics.portal_breakdown.items(), key=lambda x: x[1]["total"], reverse=True):
                lines.append(
                    f"| {portal} | {stats['total']} | {stats['interviewing']} | {stats['offers']} | {stats['rejections']} | {stats.get('conversion_rate_pct', 0.0):.1f}% |"
                )
        else:
            lines.append("| None | 0 | 0 | 0 | 0 | 0.0% |")

        lines.extend([
            "",
            "## Status Breakdown",
        ])
        for status, count in sorted(metrics.status_breakdown.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- `{status}`: {count}")

        return "\n".join(lines)
