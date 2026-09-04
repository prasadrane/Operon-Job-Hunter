"""Unit tests for submission audit logging."""

import importlib
import os
import tempfile
import pytest

# Dynamic imports because module directories start with digits (4_submission)
audit_mod = importlib.import_module("src.pipeline.4_submission.submission_audit")
AuditEntry = audit_mod.AuditEntry
SubmissionAuditor = audit_mod.SubmissionAuditor
log_audit = audit_mod.log_audit


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def auditor(temp_db):
    """Create a SubmissionAuditor with temp DB."""
    return SubmissionAuditor(db_path=temp_db)


def test_audit_entry_creation():
    """Test AuditEntry dataclass creation with defaults."""
    entry = AuditEntry(
        submission_id="sub-123",
        action_type="navigate",
        target="https://example.com/job",
        success=True,
    )
    assert entry.submission_id == "sub-123"
    assert entry.action_type == "navigate"
    assert entry.target == "https://example.com/job"
    assert entry.success is True
    assert entry.id  # UUID auto-generated
    assert entry.timestamp  # Timestamp auto-generated


def test_audit_entry_to_dict():
    """Test AuditEntry serialization to dict."""
    entry = AuditEntry(
        submission_id="sub-456",
        action_type="fill_field",
        target="input[name='email']",
        success=True,
        job_id="job-789",
        company="TestCorp",
        portal_type="greenhouse",
        tier="T2",
        step_index=3,
        duration_ms=150.5,
        metadata={"value_length": 20},
    )
    d = entry.to_dict()
    assert d["submission_id"] == "sub-456"
    assert d["action_type"] == "fill_field"
    assert d["target"] == "input[name='email']"
    assert d["success"] is True
    assert d["job_id"] == "job-789"
    assert d["company"] == "TestCorp"
    assert d["tier"] == "T2"
    assert d["step_index"] == 3
    assert d["duration_ms"] == 150.5
    assert d["metadata"]["value_length"] == 20


def test_auditor_log_and_retrieve(auditor):
    """Test logging audit entries and retrieving by submission_id."""
    entry1 = AuditEntry(
        submission_id="sub-abc",
        action_type="navigate",
        target="https://example.com",
        success=True,
        job_id="job-1",
        company="Corp1",
        step_index=1,
    )
    entry2 = AuditEntry(
        submission_id="sub-abc",
        action_type="fill_field",
        target="input[name='name']",
        success=True,
        job_id="job-1",
        company="Corp1",
        step_index=2,
    )
    entry3 = AuditEntry(
        submission_id="sub-xyz",
        action_type="submit",
        target="button[type='submit']",
        success=False,
        job_id="job-2",
        company="Corp2",
        error_detail="Form validation failed",
    )

    auditor.log_entry(entry1)
    auditor.log_entry(entry2)
    auditor.log_entry(entry3)

    # Retrieve by submission
    entries_abc = auditor.get_entries_by_submission("sub-abc")
    assert len(entries_abc) == 2
    assert entries_abc[0].action_type == "navigate"
    assert entries_abc[1].action_type == "fill_field"

    entries_xyz = auditor.get_entries_by_submission("sub-xyz")
    assert len(entries_xyz) == 1
    assert entries_xyz[0].success is False
    assert entries_xyz[0].error_detail == "Form validation failed"


def test_auditor_get_entries_by_job(auditor):
    """Test retrieving audit entries by job_id."""
    for i in range(3):
        auditor.log_entry(AuditEntry(
            submission_id=f"sub-{i}",
            action_type="navigate",
            target=f"https://example.com/{i}",
            success=True,
            job_id="job-target",
            step_index=i,
        ))
    auditor.log_entry(AuditEntry(
        submission_id="sub-other",
        action_type="navigate",
        target="https://other.com",
        success=True,
        job_id="job-other",
    ))

    entries = auditor.get_entries_by_job("job-target")
    assert len(entries) == 3
    assert all(e.job_id == "job-target" for e in entries)


def test_auditor_get_stats(auditor):
    """Test aggregate audit statistics."""
    auditor.log_entry(AuditEntry(
        submission_id="sub-1", action_type="navigate", target="url", success=True,
        tier="T2", duration_ms=100.0,
    ))
    auditor.log_entry(AuditEntry(
        submission_id="sub-1", action_type="fill_field", target="field", success=True,
        tier="T2", duration_ms=200.0,
    ))
    auditor.log_entry(AuditEntry(
        submission_id="sub-1", action_type="submit", target="button", success=False,
        tier="T2", duration_ms=50.0,
    ))

    stats = auditor.get_stats()
    assert stats["total"] == 3
    assert stats["failed"] == 1
    assert stats["success_rate"] == pytest.approx(2 / 3)
    assert stats["by_action"]["navigate"] == 1
    assert stats["by_action"]["fill_field"] == 1
    assert stats["by_action"]["submit"] == 1
    assert stats["by_tier"]["T2"] == 3
    assert stats["avg_duration_ms"]["navigate"] == 100.0


def test_log_audit_public_api(temp_db):
    """Test the log_audit() public API function."""
    entry = log_audit(
        submission_id="sub-api-test",
        action_type="click",
        target="button#submit",
        success=True,
        job_id="job-api",
        company="APICorp",
        portal_type="lever",
        tier="T2",
        step_index=5,
        duration_ms=75.0,
        metadata={"text": "Submit Application"},
        db_path=temp_db,
    )
    assert entry.submission_id == "sub-api-test"
    assert entry.action_type == "click"
    assert entry.success is True

    # Verify persisted
    auditor = SubmissionAuditor(db_path=temp_db)
    entries = auditor.get_entries_by_submission("sub-api-test")
    assert len(entries) == 1
    assert entries[0].metadata.get("text") == "Submit Application"
