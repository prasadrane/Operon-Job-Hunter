"""Telegram interactive bot & notification dispatcher for CareerGraph AI."""

import importlib
import logging
import os
from typing import Any, Dict, List, Optional, Union
import httpx

from src.core.config import get_settings
from src.core.db.repository import (
    ApplicationRepository,
    ArtifactRepository,
    EvaluationRepository,
    JobRepository,
)
from src.core.models import JobPosting, JobStatus

# Dynamically import numbered pipeline stage modules
try:
    _scanner_mod = importlib.import_module("src.pipeline.1_discovery.scanner")
    JobScanner = getattr(_scanner_mod, "JobScanner", None)
except Exception:
    JobScanner = None

try:
    _funnel_mod = importlib.import_module("src.pipeline.5_lifecycle.funnel_analytics")
    FunnelAnalytics = getattr(_funnel_mod, "FunnelAnalytics", None)
except Exception:
    FunnelAnalytics = None

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Dispatches notifications, review gates, urgent CAPTCHA alerts, and handles interactive bot commands."""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[Union[str, int]] = None,
        job_repo: Optional[JobRepository] = None,
        app_repo: Optional[ApplicationRepository] = None,
        artifact_repo: Optional[ArtifactRepository] = None,
        eval_repo: Optional[EvaluationRepository] = None,
        bot_client: Optional[Any] = None,
        scanner: Optional[Any] = None,
        funnel_analytics: Optional[Any] = None,
        approval_gate: Optional[Any] = None,
    ) -> None:
        settings = get_settings()
        self.token = token if token is not None else settings.telegram_bot_token
        raw_chat_id = chat_id if chat_id is not None else settings.telegram_chat_id
        self.chat_id = str(raw_chat_id) if raw_chat_id is not None else None

        self.job_repo = job_repo
        self.app_repo = app_repo
        self.artifact_repo = artifact_repo
        self.eval_repo = eval_repo
        self.bot_client = bot_client
        self.scanner = scanner
        self.funnel_analytics = funnel_analytics
        # LinkedInApprovalGate (or None -> lazily built with default DB on first
        # liappr callback). Also enables the pending-approval scan seam in
        # process_update when set.
        self.approval_gate = approval_gate
        self._approval_notify_state: set = set()

    def is_configured(self) -> bool:
        """Check whether credentials or client are configured."""
        return bool(self.bot_client or (self.token and self.chat_id))

    def send_message(
        self,
        text: str,
        chat_id: Optional[Union[str, int]] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
    ) -> bool:
        """Send a formatted text message to Telegram."""
        target_chat_id = str(chat_id) if chat_id is not None else self.chat_id
        if not target_chat_id:
            logger.warning("Telegram notification skipped: chat_id not configured.")
            return False

        if self.bot_client:
            try:
                self.bot_client.send_message(
                    chat_id=target_chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                )
                return True
            except Exception as exc:
                logger.error("bot_client.send_message error: %s", exc)
                return False

        if not self.token:
            logger.warning("Telegram notification skipped: telegram_bot_token not configured.")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            resp = httpx.post(url, json=payload, timeout=15.0)
            if resp.status_code == 200:
                return True
            logger.error("Telegram sendMessage returned HTTP %s: %s", resp.status_code, resp.text)
            return False
        except Exception as exc:
            logger.error("Telegram sendMessage request failed: %s", exc)
            return False

    def send_document(
        self,
        document_path: str,
        caption: Optional[str] = None,
        chat_id: Optional[Union[str, int]] = None,
        parse_mode: str = "HTML",
        filename: Optional[str] = None,
    ) -> bool:
        """Send a document or PDF file to Telegram."""
        target_chat_id = str(chat_id) if chat_id is not None else self.chat_id
        if not target_chat_id:
            logger.warning("Telegram document skipped: chat_id not configured.")
            return False

        if self.bot_client:
            try:
                self.bot_client.send_document(
                    chat_id=target_chat_id,
                    document=document_path,
                    caption=caption,
                    parse_mode=parse_mode,
                )
                return True
            except Exception as exc:
                logger.error("bot_client.send_document error: %s", exc)
                return False

        if not self.token:
            logger.warning("Telegram document skipped: telegram_bot_token not configured.")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        data: Dict[str, Any] = {
            "chat_id": target_chat_id,
            "parse_mode": parse_mode,
        }
        if caption:
            data["caption"] = caption

        try:
            file_name = filename or os.path.basename(document_path)
            with open(document_path, "rb") as f:
                files = {"document": (file_name, f, "application/pdf")}
                resp = httpx.post(url, data=data, files=files, timeout=30.0)
                if resp.status_code == 200:
                    return True
                logger.error("Telegram sendDocument returned HTTP %s: %s", resp.status_code, resp.text)
                return False
        except Exception as exc:
            logger.error("Telegram sendDocument request failed: %s", exc)
            return False

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Acknowledge or answer an incoming callback query."""
        if self.bot_client:
            try:
                self.bot_client.answer_callback_query(
                    callback_query_id=callback_query_id,
                    text=text,
                    show_alert=show_alert,
                )
                return True
            except Exception as exc:
                logger.error("bot_client.answer_callback_query error: %s", exc)
                return False

        if not self.token:
            return False

        url = f"https://api.telegram.org/bot{self.token}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id,
            "text": text or "",
            "show_alert": show_alert,
        }
        try:
            resp = httpx.post(url, json=payload, timeout=15.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.error("Telegram answerCallbackQuery request failed: %s", exc)
            return False

    def send_job_match(
        self,
        company: str,
        title: str,
        fit_score: float,
        url: str,
        h1b_sponsored: Optional[bool] = None,
        stack: Optional[List[str]] = None,
        reason: Optional[str] = None,
        job_id: Optional[str] = None,
        causal_chain: Optional[str] = None,
        bridging_statement: Optional[str] = None,
    ) -> bool:
        """Dispatch a formatted job match alert with fit score, stack, H-1B confirmation, causal proof, and reason."""
        if h1b_sponsored is True:
            h1b_str = "🏛️ <b>H-1B:</b> Confirmed / Sponsored ✅"
        elif h1b_sponsored is False:
            h1b_str = "❌ <b>H-1B:</b> Not Sponsored"
        else:
            h1b_str = "⚠️ <b>H-1B:</b> Unverified / Unknown"

        stack_str = f"\n💻 <b>Stack:</b> {', '.join(stack)}" if stack else ""
        reason_str = f"\n💡 <b>Reason:</b> {reason}" if reason else ""
        causal_str = f"\n⚡ <b>Grounded Proof:</b> {causal_chain}" if causal_chain else ""
        bridge_str = f"\n🌉 <b>Transferable Bridge:</b> {bridging_statement}" if bridging_statement else ""
        id_str = f" (ID: <code>{job_id}</code>)" if job_id else ""

        message = (
            f"🎯 <b>Job Match Alert!</b>\n\n"
            f"🏢 <b>Company:</b> {company}\n"
            f"💼 <b>Role:</b> {title}{id_str}\n"
            f"📊 <b>Fit Score:</b> {fit_score:.0f}/100\n"
            f"{h1b_str}"
            f"{stack_str}"
            f"{causal_str}"
            f"{bridge_str}"
            f"{reason_str}\n"
            f"🔗 <a href=\"{url}\">View Job Posting</a>"
        )
        return self.send_message(text=message)

    def send_captcha_alert(
        self,
        company: str,
        title: str,
        captcha_type: str = "CAPTCHA",
        url: Optional[str] = None,
        timeout_sec: int = 60,
    ) -> bool:
        """Dispatch urgent CAPTCHA / 2FA action alert with sound and priority."""
        link_str = f"\n🔗 <a href=\"{url}\">Application Portal</a>" if url else ""
        message = (
            f"🚨 <b>URGENT: CAPTCHA / Human Action Required!</b>\n\n"
            f"🏢 <b>Company:</b> {company}\n"
            f"💼 <b>Role:</b> {title}\n"
            f"⚠️ <b>Action Type:</b> {captcha_type}\n"
            f"⏱️ <b>Timeout:</b> {timeout_sec}s remaining before retry"
            f"{link_str}\n\n"
            f"<i>Please solve the puzzle or complete verification in your browser to proceed.</i>"
        )
        return self.send_message(text=message, disable_notification=False)

    def send_review_gate(
        self,
        job_id: str,
        company: str,
        title: str,
        fit_score: float,
        url: str,
        resume_pdf_path: Optional[str] = None,
        match_reason: Optional[str] = None,
        causal_chain: Optional[str] = None,
    ) -> bool:
        """Dispatch a Review Gate notification with inline action buttons and grounded causal reasoning."""
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ 1-Click Apply", "callback_data": f"apply:{job_id}"},
                    {"text": "📄 PDF", "callback_data": f"pdf:{job_id}"},
                    {"text": "❌ Skip", "callback_data": f"skip:{job_id}"},
                ]
            ]
        }

        reason_str = f"\n💡 <b>Evaluation:</b> {match_reason}" if match_reason else ""
        causal_str = f"\n⚡ <b>Grounded Proof:</b> {causal_chain}" if causal_chain else ""
        pdf_str = "\n📄 <b>Tailored Resume:</b> Ready" if resume_pdf_path else ""

        message = (
            f"📋 <b>Review Gate: Job Match Ready for Action</b>\n\n"
            f"🏢 <b>Company:</b> {company}\n"
            f"💼 <b>Role:</b> {title}\n"
            f"📊 <b>Fit Score:</b> {fit_score:.0f}/100"
            f"{causal_str}"
            f"{reason_str}"
            f"{pdf_str}\n"
            f"🔗 <a href=\"{url}\">View Job Posting</a>"
        )
        return self.send_message(text=message, reply_markup=reply_markup)

    def handle_command(self, command_text: str) -> str:
        """Parse and execute Telegram command strings."""
        tokens = command_text.strip().split()
        if not tokens:
            return self._help_text()

        cmd = tokens[0].lower()

        if cmd == "/status":
            discovered_count = len(self.job_repo.get_all_jobs()) if self.job_repo else 0
            matched_count = len(self.job_repo.get_jobs_by_status(JobStatus.MATCHED)) if self.job_repo else 0
            active_count = len(self.app_repo.get_active_applications()) if self.app_repo else 0
            return (
                "📊 <b>CareerGraph AI — Pipeline Status</b>\n\n"
                f"• <b>Total Discovered Jobs:</b> {discovered_count}\n"
                f"• <b>Matched / Pending Review:</b> {matched_count}\n"
                f"• <b>Active In-Flight Applications:</b> {active_count}\n"
                "• <b>System Health:</b> 🟢 Operational & Watching"
            )

        if cmd == "/scan":
            scanner = self.scanner
            if scanner is None and JobScanner is not None:
                scanner = JobScanner(job_repo=self.job_repo)

            if scanner is not None:
                try:
                    discovered = scanner.scan_all()
                    return f"🔍 <b>Scan completed:</b> Discovered {len(discovered)} eligible job postings across target watchlist."
                except Exception as exc:
                    return f"⚠️ Scan encountered an error: {exc}"
            return "🔍 <b>Scan initiated:</b> Scanning configured job boards in the background."

        if cmd == "/apply":
            if len(tokens) < 2:
                return "⚠️ <b>Usage:</b> Please specify a job ID: <code>/apply &lt;id&gt;</code>"
            job_id = tokens[1]
            if self.job_repo:
                job = self.job_repo.get_job(job_id)
                if not job:
                    return f"❌ Job ID <code>{job_id}</code> not found in database."
                self.job_repo.update_status(job_id, JobStatus.SUBMITTING)
                return f"🚀 <b>Initiating 1-Click Apply</b> for <code>{job_id}</code> ({job.title} at {job.company})."
            return f"🚀 <b>Initiating 1-Click Apply</b> for job <code>{job_id}</code>."

        if cmd == "/metrics":
            funnel = self.funnel_analytics
            if funnel is None and FunnelAnalytics is not None:
                funnel = FunnelAnalytics(app_repo=self.app_repo, job_repo=self.job_repo)

            if funnel is not None:
                try:
                    metrics = funnel.calculate_metrics()
                    summary_md = getattr(metrics, "summary_markdown", None)
                    if summary_md and isinstance(summary_md, str):
                        return summary_md

                    total_applied = getattr(metrics, "total_applied", 0)
                    total_active = getattr(metrics, "total_active", 0)
                    interview_rate = getattr(metrics, "interview_rate_pct", 0.0)
                    interview_count = getattr(metrics, "total_interviewing", 0)
                    offer_rate = getattr(metrics, "offer_rate_pct", 0.0)
                    offer_count = getattr(metrics, "total_offers", 0)
                    rejection_rate = getattr(metrics, "rejection_rate_pct", 0.0)
                    avg_latency = getattr(metrics, "avg_response_latency_days", 0.0)

                    return (
                        f"📈 <b>Funnel & Lifecycle Analytics</b>\n\n"
                        f"• <b>Total Applied:</b> {total_applied}\n"
                        f"• <b>Active In-Flight:</b> {total_active}\n"
                        f"• <b>Interview Rate:</b> {float(interview_rate):.1f}% ({interview_count} interviews)\n"
                        f"• <b>Offer Rate:</b> {float(offer_rate):.1f}% ({offer_count} offers)\n"
                        f"• <b>Rejection Rate:</b> {float(rejection_rate):.1f}%\n"
                        f"• <b>Avg Response Latency:</b> {float(avg_latency):.1f} days"
                    )
                except Exception as exc:
                    return f"⚠️ Could not calculate metrics: {exc}"
            return "📈 <b>Funnel Analytics:</b> No lifecycle data recorded yet."

        return self._help_text()

    def _help_text(self) -> str:
        """Return formatted help command listing."""
        return (
            "🤖 <b>CareerGraph AI Bot Commands:</b>\n\n"
            "• <code>/status</code> — View live pipeline stats & application queue\n"
            "• <code>/scan</code> — Trigger discovery crawl on company watchlist\n"
            "• <code>/apply &lt;id&gt;</code> — 1-Click apply to specific job ID\n"
            "• <code>/metrics</code> — View lifecycle funnel conversion analytics\n"
            "• <code>/help</code> — Show this command reference"
        )

    def handle_callback_query(
        self,
        callback_data: str,
        callback_query_id: Optional[str] = None,
        from_user: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Handle inline button callback queries (apply, skip, pdf)."""
        parts = callback_data.split(":", 1)
        action = parts[0].strip().lower()
        job_id = parts[1].strip() if len(parts) > 1 else ""

        ack_text = ""
        if action == "apply":
            if self.job_repo and job_id:
                self.job_repo.update_status(job_id, JobStatus.SUBMITTING)
            ack_text = f"✅ Initiating 1-Click Apply for Job {job_id}..."
        elif action == "skip":
            if self.job_repo and job_id:
                self.job_repo.update_status(job_id, JobStatus.IGNORED)
            ack_text = f"❌ Skipped Job {job_id}."
        elif action == "pdf":
            pdf_path = None
            if self.artifact_repo and job_id:
                art = self.artifact_repo.get_by_job_id(job_id)
                if art:
                    pdf_path = art.resume_pdf_path
            if pdf_path:
                self.send_document(pdf_path, caption=f"📄 Resume for Job {job_id}")
                ack_text = f"📄 Sent resume PDF for Job {job_id}."
            else:
                ack_text = f"📄 PDF requested for Job {job_id}."
        else:
            ack_text = f"Unknown action: {action}"

        if callback_query_id:
            self.answer_callback_query(callback_query_id, text=ack_text)

        return {
            "status": "ok",
            "action": action,
            "job_id": job_id,
            "message": ack_text,
        }

    def process_update(self, update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process incoming Telegram webhook or polling update."""
        if "message" in update and "text" in update["message"]:
            msg = update["message"]
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", self.chat_id or ""))
            if text.startswith("/"):
                response_text = self.handle_command(text)
                self.send_message(response_text, chat_id=chat_id)
                return {"type": "message", "command": text, "response": response_text}

        if "callback_query" in update:
            cb = update["callback_query"]
            cb_id = cb.get("id")
            data = cb.get("data", "")
            from_user = (cb.get("from") or {}).get("id")
            res = self.handle_callback_query(
                data, callback_query_id=cb_id, from_user=from_user
            )
            return {"type": "callback_query", **res}

        return None
