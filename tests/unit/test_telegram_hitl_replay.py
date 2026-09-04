"""Unit tests for Telegram HITL Bot Idempotency, SQLite Locks, and Fallback Bundle Generator."""

import time
import concurrent.futures
import pytest
from src.core.db.dual_engine import init_dual_database_pool, get_connection
from src.interface.bot.fallback_bundle import FallbackBundleGenerator
from src.interface.bot.telegram_hitl import TelegramHITLManager


def test_fallback_bundle_generation():
    """Verify fallback bundle generation contains job URL, resume path, clipboard text, and tappable <code> HTML."""
    generator = FallbackBundleGenerator()
    state = {
        "job_id": "job_123",
        "company": "Figma",
        "title": "Senior Backend Engineer",
        "url": "https://jobs.lever.co/figma/123",
        "resume_pdf_path": "./data/artifacts/Figma_Resume.pdf",
        "cover_letter_path": "./data/artifacts/Figma_CoverLetter.pdf",
        "qa_answers": {"relocation": "No", "sponsorship": "Yes", "salary_expectation": "$180,000"}
    }
    bundle = generator.generate(state)
    
    assert bundle["job_url"] == state["url"]
    assert "Figma_Resume.pdf" in bundle["resume_path"]
    assert bundle["cover_letter_path"] == state["cover_letter_path"]
    assert "sponsorship: Yes" in bundle["clipboard_text"]
    assert "salary_expectation: $180,000" in bundle["clipboard_text"]
    
    # HTML formatted message with tappable <code> tags for easy 1-click mobile copy
    html_msg = bundle["html_message"]
    assert "<b>Figma</b>" in html_msg or "<b>Company:</b> Figma" in html_msg or "Figma" in html_msg
    assert "<code>No</code>" in html_msg
    assert "<code>Yes</code>" in html_msg
    assert "<code>$180,000</code>" in html_msg
    assert f"<a href=\"{state['url']}\">" in html_msg or state["url"] in html_msg


def test_fallback_bundle_with_missing_fields_defaults():
    """Verify fallback bundle handles empty or partial states safely."""
    generator = FallbackBundleGenerator()
    bundle = generator.generate({})
    assert bundle["job_url"] == ""
    assert bundle["resume_path"] == ""
    assert bundle["clipboard_text"] is not None
    assert bundle["html_message"] is not None


def test_fallback_bundle_tappable_field_dictionary():
    """Verify generator provides individual tappable field dictionary for quick lookup."""
    generator = FallbackBundleGenerator()
    state = {
        "job_id": "job_456",
        "company": "Stripe",
        "title": "Staff Engineer",
        "url": "https://stripe.com/jobs/456",
        "qa_answers": {"work_auth": "Authorized", "linkedin_url": "https://linkedin.com/in/candidate"}
    }
    bundle = generator.generate(state)
    fields = bundle["tappable_fields"]
    assert fields["work_auth"] == "<code>Authorized</code>"
    assert fields["linkedin_url"] == "<code>https://linkedin.com/in/candidate</code>"


def test_idempotent_approval_double_tap_lock(tmp_path):
    """Verify in-memory / SQLite approval lock prevents double-submission race conditions."""
    db_path = str(tmp_path / "checkpoints.db")
    init_dual_database_pool(checkpoints_path=db_path, telemetry_path=str(tmp_path / "telemetry.db"))
    
    manager = TelegramHITLManager(db_path=db_path)
    job_id = "job_test_123"
    
    # First tap succeeds
    assert manager.acquire_submission_lock(job_id, locked_by="user_telegram_01") is True
    assert manager.is_locked(job_id) is True
    
    # Double tap fails immediately
    assert manager.acquire_submission_lock(job_id, locked_by="user_telegram_01") is False
    
    # Check lock info
    info = manager.get_lock_info(job_id)
    assert info is not None
    assert info["job_id"] == job_id
    assert info["locked_by"] == "user_telegram_01"
    
    # Release lock
    assert manager.release_lock(job_id) is True
    assert manager.is_locked(job_id) is False
    
    # Acquire lock again succeeds after release
    assert manager.acquire_submission_lock(job_id, locked_by="user_telegram_02") is True


def test_sqlite_persistence_atomic_lock(tmp_path):
    """Verify SQLite persistence reflects lock across distinct TelegramHITLManager instances."""
    db_path = str(tmp_path / "checkpoints.db")
    init_dual_database_pool(checkpoints_path=db_path, telemetry_path=str(tmp_path / "telemetry.db"))
    
    manager1 = TelegramHITLManager(db_path=db_path)
    manager2 = TelegramHITLManager(db_path=db_path)
    
    job_id = "job_cross_instance_999"
    assert manager1.acquire_submission_lock(job_id, locked_by="worker_1") is True
    
    # manager2 sees the lock in SQLite
    assert manager2.is_locked(job_id) is True
    assert manager2.acquire_submission_lock(job_id, locked_by="worker_2") is False
    
    # Verify in database table directly
    with get_connection("checkpoints") as conn:
        row = conn.execute("SELECT job_id, locked_by FROM job_locks WHERE job_id = ?", (job_id,)).fetchone()
        assert row is not None
        assert row[0] == job_id
        assert row[1] == "worker_1"
        
    manager1.release_lock(job_id)
    assert manager2.is_locked(job_id) is False


def test_lock_expiration_and_timeout(tmp_path):
    """Verify expired locks automatically timeout and permit re-acquisition."""
    db_path = str(tmp_path / "checkpoints.db")
    init_dual_database_pool(checkpoints_path=db_path, telemetry_path=str(tmp_path / "telemetry.db"))
    
    manager = TelegramHITLManager(db_path=db_path)
    job_id = "job_expiring_001"
    
    # Acquire lock with 1 second TTL
    assert manager.acquire_submission_lock(job_id, ttl_seconds=1) is True
    assert manager.is_locked(job_id) is True
    
    # Wait for TTL to expire
    time.sleep(1.2)
    
    # Lock is expired
    assert manager.is_locked(job_id) is False
    # Re-acquisition succeeds
    assert manager.acquire_submission_lock(job_id, ttl_seconds=60) is True


def test_concurrent_threads_double_tap_race_condition(tmp_path):
    """Verify thread safety under heavy concurrent taps: exactly 1 thread acquires the lock."""
    db_path = str(tmp_path / "checkpoints.db")
    init_dual_database_pool(checkpoints_path=db_path, telemetry_path=str(tmp_path / "telemetry.db"))
    
    manager = TelegramHITLManager(db_path=db_path)
    job_id = "job_concurrency_race"
    num_threads = 20
    
    def try_acquire(worker_id: int) -> bool:
        return manager.acquire_submission_lock(job_id, locked_by=f"worker_{worker_id}")
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(try_acquire, i) for i in range(num_threads)]
        results = [f.result() for f in futures]
        
    success_count = sum(1 for r in results if r is True)
    failure_count = sum(1 for r in results if r is False)
    
    assert success_count == 1
    assert failure_count == num_threads - 1


def test_release_nonexistent_lock(tmp_path):
    """Verify releasing an unacquired or nonexistent lock returns False safely."""
    db_path = str(tmp_path / "checkpoints.db")
    init_dual_database_pool(checkpoints_path=db_path, telemetry_path=str(tmp_path / "telemetry.db"))
    
    manager = TelegramHITLManager(db_path=db_path)
    assert manager.release_lock("nonexistent_job_xyz") is False
