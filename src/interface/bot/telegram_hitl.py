"""Idempotent Telegram HITL Manager with SQLite atomic job locks and thread safety."""

from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, Generator, Optional

from src.core.db.dual_engine import get_connection

logger = logging.getLogger(__name__)


class TelegramHITLManager:
    """Manages idempotent review gates and submission locks to prevent double-tap race conditions."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._thread_lock = threading.Lock()
        self._pending_2fa_requests: Dict[str, Dict[str, Any]] = {}
        self._2fa_responses: Dict[str, str] = {}
        self._ensure_table()

    @contextmanager
    def _get_db(self) -> Generator[sqlite3.Connection, None, None]:
        """Obtain a SQLite connection either from custom db_path or default dual_engine pool."""
        if self.db_path:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("PRAGMA busy_timeout = 30000;")
            try:
                yield conn
            finally:
                conn.close()
        else:
            with get_connection("checkpoints") as conn:
                yield conn

    def _ensure_table(self) -> None:
        """Ensure the job_locks table exists."""
        try:
            with self._get_db() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS job_locks (
                        job_id TEXT PRIMARY KEY,
                        locked_by TEXT,
                        locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP
                    );
                    """
                )
                conn.commit()
        except Exception as exc:
            logger.warning("Failed ensuring job_locks table: %s", exc)

    def acquire_submission_lock(
        self, job_id: str, locked_by: str = "telegram_user", ttl_seconds: int = 300
    ) -> bool:
        """Atomically acquire an idempotent submission lock. Returns True if acquired, False otherwise."""
        with self._thread_lock:
            try:
                with self._get_db() as conn:
                    now = datetime.utcnow()
                    now_str = now.isoformat()
                    expires_str = (now + timedelta(seconds=ttl_seconds)).isoformat()

                    # Check existing lock
                    cursor = conn.execute(
                        "SELECT job_id, locked_by, expires_at FROM job_locks WHERE job_id = ?",
                        (job_id,),
                    )
                    row = cursor.fetchone()

                    if row:
                        expires_at = row[2]
                        if expires_at:
                            try:
                                exp_dt = datetime.fromisoformat(expires_at)
                                if exp_dt > now:
                                    # Lock is still active and valid
                                    return False
                            except (ValueError, TypeError):
                                pass

                        # Lock expired, update atomically
                        conn.execute(
                            """
                            UPDATE job_locks
                            SET locked_by = ?, locked_at = ?, expires_at = ?
                            WHERE job_id = ?
                            """,
                            (locked_by, now_str, expires_str, job_id),
                        )
                        conn.commit()
                        return True
                    else:
                        # Insert new lock
                        conn.execute(
                            """
                            INSERT INTO job_locks (job_id, locked_by, locked_at, expires_at)
                            VALUES (?, ?, ?, ?)
                            """,
                            (job_id, locked_by, now_str, expires_str),
                        )
                        conn.commit()
                        return True
            except sqlite3.IntegrityError:
                return False
            except Exception as exc:
                logger.error("Error acquiring lock for job %s: %s", job_id, exc)
                return False

    def release_lock(self, job_id: str) -> bool:
        """Release a previously acquired lock. Returns True if a lock was deleted, False otherwise."""
        with self._thread_lock:
            try:
                with self._get_db() as conn:
                    cursor = conn.execute(
                        "DELETE FROM job_locks WHERE job_id = ?", (job_id,)
                    )
                    conn.commit()
                    return cursor.rowcount > 0
            except Exception as exc:
                logger.error("Error releasing lock for job %s: %s", job_id, exc)
                return False

    def is_locked(self, job_id: str) -> bool:
        """Check whether a valid unexpired lock exists for the specified job_id."""
        with self._thread_lock:
            try:
                with self._get_db() as conn:
                    cursor = conn.execute(
                        "SELECT job_id, expires_at FROM job_locks WHERE job_id = ?",
                        (job_id,),
                    )
                    row = cursor.fetchone()
                    if not row:
                        return False

                    expires_at = row[1]
                    if not expires_at:
                        return True

                    try:
                        exp_dt = datetime.fromisoformat(expires_at)
                        if exp_dt <= datetime.utcnow():
                            # Stale/expired lock, clean it up
                            conn.execute(
                                "DELETE FROM job_locks WHERE job_id = ?", (job_id,)
                            )
                            conn.commit()
                            return False
                        return True
                    except (ValueError, TypeError):
                        return True
            except Exception as exc:
                logger.error("Error checking lock for job %s: %s", job_id, exc)
                return False

    def get_lock_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve details of an active lock if one exists."""
        with self._thread_lock:
            try:
                with self._get_db() as conn:
                    cursor = conn.execute(
                        "SELECT job_id, locked_by, locked_at, expires_at FROM job_locks WHERE job_id = ?",
                        (job_id,),
                    )
                    row = cursor.fetchone()
                    if not row:
                        return None

                    job_id_val, locked_by, locked_at, expires_at = row
                    if expires_at:
                        try:
                            exp_dt = datetime.fromisoformat(expires_at)
                            if exp_dt <= datetime.utcnow():
                                return None
                        except (ValueError, TypeError):
                            pass

                    return {
                        "job_id": job_id_val,
                        "locked_by": locked_by,
                        "locked_at": locked_at,
                        "expires_at": expires_at,
                    }
            except Exception as exc:
                logger.error("Error retrieving lock info for job %s: %s", job_id, exc)
                return None

    # ── 2FA / TOTP support ─────────────────────────────────────────────────

    def _send_telegram_message(self, text: str) -> Optional[Dict[str, Any]]:
        """Send a Telegram message. Override or mock for testing.

        Returns dict with message_id on success, None on failure.
        """
        try:
            from src.core.config import get_settings
            settings = get_settings()
            token = getattr(settings, "telegram_bot_token", None)
            chat_id = getattr(settings, "telegram_chat_id", None)
            if not token or not chat_id:
                logger.warning("Telegram not configured (missing token/chat_id)")
                return None

            import urllib.request
            import urllib.parse
            import json

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }).encode()
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                if result.get("ok"):
                    msg_id = str(result["result"]["message_id"])
                    return {"message_id": msg_id}
                logger.warning("Telegram sendMessage failed: %s", result)
                return None
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc)
            return None

    def send_2fa_request(self, portal_type: str, job_id: str) -> Optional[str]:
        """Send a 2FA request notification via Telegram.

        Args:
            portal_type: Portal name (e.g. "linkedin", "indeed")
            job_id: Job identifier for context

        Returns:
            message_id string on success, None on failure
        """
        text = (
            f"<b>🔐 2FA Required</b>\n\n"
            f"Portal: <b>{portal_type.title()}</b>\n"
            f"Job ID: {job_id or 'N/A'}\n\n"
            f"Please reply with the SMS/authenticator code."
        )

        result = self._send_telegram_message(text)
        if not result:
            return None

        message_id = result["message_id"]
        self._pending_2fa_requests[message_id] = {
            "portal_type": portal_type,
            "job_id": job_id,
            "requested_at": time.time(),
        }
        logger.info("Sent 2FA request for portal=%s job=%s msg_id=%s", portal_type, job_id, message_id)
        return message_id

    def wait_for_2fa_response(self, message_id: str, timeout_sec: int = 60) -> Optional[str]:
        """Wait for user to reply with 2FA code via Telegram.

        In production this is driven by webhook/polling callbacks.
        This method polls _2fa_responses for a matching message_id.

        Args:
            message_id: The message_id returned by send_2fa_request
            timeout_sec: How long to wait (default 60s)

        Returns:
            The 2FA code string, or None on timeout
        """
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            code = self._2fa_responses.pop(message_id, None)
            if code is not None:
                logger.info("Received 2FA response for msg_id=%s", message_id)
                self._pending_2fa_requests.pop(message_id, None)
                return code
            time.sleep(1)

        logger.warning("2FA response timeout for msg_id=%s", message_id)
        self._pending_2fa_requests.pop(message_id, None)
        return None

    def submit_2fa_response(self, message_id: str, code: str) -> None:
        """Submit a 2FA response (called by Telegram webhook/polling handler).

        Args:
            message_id: The message_id this is a reply to
            code: The 2FA code entered by user
        """
        if message_id in self._pending_2fa_requests:
            self._2fa_responses[message_id] = code
            logger.info("2FA response stored for msg_id=%s", message_id)
