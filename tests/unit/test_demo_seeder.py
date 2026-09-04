from pathlib import Path

from src.core.db.repository import JobRepository
from src.demo.seeder import seed_demo, DEMO_JOB_COUNT


def test_seed_demo_inserts_20_jobs_and_profile(tmp_path):
    db = tmp_path / "demo.db"
    jobs = seed_demo(db_path=str(db))
    assert len(jobs) == DEMO_JOB_COUNT == 20
    repo = JobRepository(str(db))
    for job in jobs:
        assert job.id.startswith("demo_")
        assert job.company not in {"", None}
        assert job.description and len(job.description) > 200


def test_seed_demo_two_jobs_target_mock_ats(tmp_path):
    jobs = seed_demo(db_path=str(tmp_path / "demo.db"), ats_base_url="http://127.0.0.1:9")
    portal_jobs = [j for j in jobs if j.portal_type in {"greenhouse", "lever"}]
    assert len(portal_jobs) == 2
    assert all(j.url.startswith("http://127.0.0.1:9/") for j in portal_jobs)


def test_seed_demo_is_idempotent(tmp_path):
    db = str(tmp_path / "demo.db")
    seed_demo(db_path=db)
    jobs2 = seed_demo(db_path=db)
    repo = JobRepository(db)
    assert len(jobs2) == 20  # re-seed upserts, no duplicates
