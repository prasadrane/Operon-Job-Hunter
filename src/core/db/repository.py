"""Repository implementations for CareerGraph AI SQLite persistence."""

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from urllib.parse import urlparse
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Union

COMMON_TECH_TAGS = [
    "AWS", "ECS", "Lambda", "DynamoDB", "Kafka", "MSK", "Docker", "Kubernetes",
    ".NET 9", ".NET 8", ".NET Core", ".NET", "C#", "ASP.NET", "Microservices",
    "FastAPI", "Python", "TypeScript", "Angular", "SQL Server", "PostgreSQL", "GraphQL",
    "REST", "OAuth2", "JWT", "Bedrock", "Claude", "GraphRAG", "Dynatrace",
    "OpenTelemetry", "Splunk", "PagerDuty", "Terraform", "CI/CD", "GitHub Actions",
    "TDD", "Clean Architecture", "Distributed Systems", "Golang", "Java", "React", "Next.js",
    "Redis", "Elasticsearch", "gRPC", "Linux"
]

def extract_quick_keywords(text: str) -> List[str]:
    """Fast regex extraction of top technical keywords for un-evaluated jobs."""
    if not text:
        return []
    found = []
    text_lower = text.lower()
    for kw in COMMON_TECH_TAGS:
        pat = re.compile(rf"\b{re.escape(kw.lower())}\b")
        if pat.search(text_lower):
            found.append(kw)
    return found[:5]

def extract_quick_seniority(title: str) -> Optional[str]:
    """Infer seniority level from job title."""
    if not title:
        return None
    t_low = title.lower()
    if "staff" in t_low or "principal" in t_low:
        return "Staff / Principal"
    if "lead" in t_low:
        return "Lead"
    if "senior" in t_low or "sr" in t_low:
        return "Senior"
    if "director" in t_low or "vp" in t_low or "head" in t_low:
        return "Director"
    if "manager" in t_low:
        return "Manager"
    if "intern" in t_low:
        return "Intern"
    return "Mid-Level"

from src.core.db.schema import init_db
from src.core.models import (
    ApplicationRecord,
    EvaluationResult,
    JobPosting,
    JobStatus,
    TailoredArtifacts,
)


def _format_dt(dt: Optional[datetime]) -> Optional[str]:
    """Convert datetime object to ISO-8601 string."""
    if dt is None:
        return None
    return dt.isoformat()


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 string into datetime object."""
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


def _dump_json(obj: Any) -> Optional[str]:
    """Serialize object to JSON string."""
    if obj is None:
        return None
    return json.dumps(obj)


def _load_json(val: Optional[str], default: Any = None) -> Any:
    """Deserialize JSON string to Python object."""
    if not val:
        return default
    try:
        return json.loads(val)
    except Exception:
        return default


class BaseRepository:
    """Base SQLite repository providing connection handling and pragmas."""

    def __init__(self, db_path: str = "./data/careergraph.db"):
        self.db_path = db_path
        init_db(self.db_path)

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for SQLite connections with WAL and foreign keys enabled."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class JobRepository(BaseRepository):
    """Repository managing job posting records and status transitions."""

    def insert_job(self, job: JobPosting) -> JobPosting:
        """Insert or replace a job posting record."""
        with self.connection() as conn:
            h1b_val = (
                1 if job.h1b_sponsored is True else (0 if job.h1b_sponsored is False else None)
            )
            raw_data_str = _dump_json(job.raw_data)
            posted_at_str = _format_dt(job.posted_at)
            discovered_at_str = _format_dt(job.discovered_at) or datetime.utcnow().isoformat()
            created_at_str = _format_dt(job.created_at)
            updated_at_str = _format_dt(job.updated_at)
            status_val = (
                job.status.value if isinstance(job.status, JobStatus) else str(job.status)
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO jobs (
                    id, company, title, url, portal_type, source, status,
                    location, description, h1b_sponsored, posted_at, discovered_at,
                    created_at, updated_at, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    job.id,
                    job.company,
                    job.title,
                    job.url,
                    job.portal_type,
                    job.source,
                    status_val,
                    job.location,
                    job.description,
                    h1b_val,
                    posted_at_str,
                    discovered_at_str,
                    created_at_str,
                    updated_at_str,
                    raw_data_str,
                ),
            )
        return job

    def bulk_upsert_jobs(self, jobs: List[JobPosting]) -> int:
        """Efficiently bulk insert or replace job postings in a single transaction."""
        if not jobs:
            return 0
        now_str = datetime.utcnow().isoformat()
        rows = []
        for job in jobs:
            h1b_val = (
                1 if job.h1b_sponsored is True else (0 if job.h1b_sponsored is False else None)
            )
            raw_data_str = _dump_json(job.raw_data)
            posted_at_str = _format_dt(job.posted_at)
            discovered_at_str = _format_dt(job.discovered_at) or now_str
            created_at_str = _format_dt(job.created_at) or now_str
            updated_at_str = _format_dt(job.updated_at) or now_str
            status_val = (
                job.status.value if isinstance(job.status, JobStatus) else str(job.status)
            )
            rows.append((
                job.id,
                job.company,
                job.title,
                job.url,
                job.portal_type,
                job.source,
                status_val,
                job.location,
                job.description,
                h1b_val,
                posted_at_str,
                discovered_at_str,
                created_at_str,
                updated_at_str,
                raw_data_str,
            ))
        with self.connection() as conn:
            cursor = conn.executemany(
                """
                INSERT OR REPLACE INTO jobs (
                    id, company, title, url, portal_type, source, status,
                    location, description, h1b_sponsored, posted_at, discovered_at,
                    created_at, updated_at, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows,
            )
            return cursor.rowcount

    def get_latest_job_posted_at(
        self, company: Optional[str] = None, portal_type: Optional[str] = None
    ) -> Optional[datetime]:
        """Fetch the most recent posted_at timestamp for delta crawling high-water mark."""
        query = "SELECT MAX(posted_at) as max_posted FROM jobs WHERE posted_at IS NOT NULL"
        params: List[Any] = []
        if company:
            query += " AND company = ?"
            params.append(company)
        if portal_type:
            query += " AND portal_type = ?"
            params.append(portal_type)
        with self.connection() as conn:
            cursor = conn.execute(query, tuple(params))
            row = cursor.fetchone()
            if row and row["max_posted"]:
                return _parse_dt(row["max_posted"])
        return None

    def get_job(self, job_id: str) -> Optional[JobPosting]:
        """Fetch a job posting by its ID with joined evaluation data."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                SELECT j.*, e.fit_score as eval_fit_score, e.reason as eval_reason, 
                       e.block_scores as eval_block_scores, e.work_auth_blocker as eval_auth, 
                       e.is_ghost_job as eval_ghost
                FROM jobs j
                LEFT JOIN evaluations e ON j.id = e.job_id
                WHERE j.id = ?
                LIMIT 1;
                """,
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def find_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """P5b tracker lookup: exact url, then canonical path suffix. Returns a
        plain dict (lighter than _row_to_job's eval join) for event payload use."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM jobs WHERE url = ? LIMIT 1", (url,))
            row = cursor.fetchone()
            if row is None:
                path = urlparse(url).path
                cursor = conn.execute(
                    "SELECT * FROM jobs WHERE url LIKE ? LIMIT 1", (f"%{path}",))
                row = cursor.fetchone()
        return dict(row) if row else None

    def get_job_by_url(self, url: str) -> Optional[JobPosting]:
        """Fetch a job posting by its URL with joined evaluation data."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                SELECT j.*, e.fit_score as eval_fit_score, e.reason as eval_reason, 
                       e.block_scores as eval_block_scores, e.work_auth_blocker as eval_auth, 
                       e.is_ghost_job as eval_ghost
                FROM jobs j
                LEFT JOIN evaluations e ON j.id = e.job_id
                WHERE j.url = ?
                LIMIT 1;
                """,
                (url,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def is_duplicate(self, url: str) -> bool:
        """Check whether a job with the specified URL already exists."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT 1 FROM jobs WHERE url = ? LIMIT 1;", (url,))
            return cursor.fetchone() is not None

    def update_status(self, job_id: str, status: Union[JobStatus, str]) -> bool:
        """Update status of a job posting."""
        status_val = status.value if isinstance(status, JobStatus) else str(status)
        now_str = datetime.utcnow().isoformat()
        with self.connection() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?;",
                (status_val, now_str, job_id),
            )
            return cursor.rowcount > 0

    def update_job(self, job: JobPosting) -> bool:
        """Update all fields of a job posting."""
        h1b_val = (
            1 if job.h1b_sponsored is True else (0 if job.h1b_sponsored is False else None)
        )
        status_val = (
            job.status.value if isinstance(job.status, JobStatus) else str(job.status)
        )
        now_str = datetime.utcnow().isoformat()

        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs SET
                    company = ?, title = ?, url = ?, portal_type = ?,
                    source = ?, status = ?, location = ?, description = ?,
                    h1b_sponsored = ?, updated_at = ?, raw_data = ?
                WHERE id = ?;
                """,
                (
                    job.company,
                    job.title,
                    job.url,
                    job.portal_type,
                    job.source,
                    status_val,
                    job.location,
                    job.description,
                    h1b_val,
                    now_str,
                    _dump_json(job.raw_data),
                    job.id,
                ),
            )
            return cursor.rowcount > 0

    def delete_job(self, job_id: str) -> bool:
        """Delete a job posting and cascade delete related records."""
        with self.connection() as conn:
            cursor = conn.execute("DELETE FROM jobs WHERE id = ?;", (job_id,))
            return cursor.rowcount > 0

    def save_profile(self, profile: Dict[str, Any]) -> None:
        """Upsert candidate profile into workday_profiles."""
        WorkdayProfileRepository(self.db_path).save_profile(profile)

    def get_profile(self) -> Dict[str, Any]:
        """Fetch candidate profile from workday_profiles."""
        return WorkdayProfileRepository(self.db_path).get_profile()


    def get_jobs_by_status(
        self, status: Union[JobStatus, str], limit: Optional[int] = None
    ) -> List[JobPosting]:
        """Fetch all jobs matching a specific status, prioritizing H-1B and recent postings."""
        status_val = status.value if isinstance(status, JobStatus) else str(status)
        query = """
            SELECT j.*, e.fit_score as eval_fit_score, e.reason as eval_reason, 
                   e.block_scores as eval_block_scores, e.work_auth_blocker as eval_auth, 
                   e.is_ghost_job as eval_ghost
            FROM jobs j
            LEFT JOIN evaluations e ON j.id = e.job_id
            WHERE j.status = ?
            ORDER BY j.h1b_sponsored DESC, j.posted_at DESC, j.discovered_at DESC
        """
        params: List[Any] = [status_val]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self.connection() as conn:
            cursor = conn.execute(query, tuple(params))
            return [self._row_to_job(r) for r in cursor.fetchall()]

    def get_all_jobs(self, limit: Optional[int] = None) -> List[JobPosting]:
        """Fetch all jobs ordered by H-1B sponsorship priority and posting recency."""
        query = """
            SELECT j.*, e.fit_score as eval_fit_score, e.reason as eval_reason, 
                   e.block_scores as eval_block_scores, e.work_auth_blocker as eval_auth, 
                   e.is_ghost_job as eval_ghost
            FROM jobs j
            LEFT JOIN evaluations e ON j.id = e.job_id
            ORDER BY j.h1b_sponsored DESC, j.posted_at DESC, j.discovered_at DESC
        """
        params: List[Any] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self.connection() as conn:
            cursor = conn.execute(query, tuple(params))
            return [self._row_to_job(r) for r in cursor.fetchall()]

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobPosting:
        """Convert a sqlite row to a JobPosting model with enriched evaluation and skill metadata."""
        h1b_raw = row["h1b_sponsored"]
        h1b = bool(h1b_raw) if h1b_raw is not None else None

        status_str = row["status"]
        try:
            status = JobStatus(status_str)
        except ValueError:
            status = JobStatus.DISCOVERED

        posted_at_val = None
        if "posted_at" in row.keys():
            posted_at_val = _parse_dt(row["posted_at"])

        row_keys = set(row.keys()) if hasattr(row, "keys") else set()
        
        fit_score = None
        matched_skills = []
        missing_skills = []
        tech_stack = []
        salary_range = None
        seniority = None
        is_ghost = None
        auth_block = None
        eval_reason = None
        
        if "eval_fit_score" in row_keys and row["eval_fit_score"] is not None:
            fit_score = float(row["eval_fit_score"])
        elif "fit_score" in row_keys and row["fit_score"] is not None:
            fit_score = float(row["fit_score"])

        block_scores = {}
        if "eval_block_scores" in row_keys and row["eval_block_scores"]:
            block_scores = _load_json(row["eval_block_scores"], default={})
        elif "block_scores" in row_keys and row["block_scores"]:
            block_scores = _load_json(row["block_scores"], default={})

        if block_scores:
            matched_skills = block_scores.get("block_b", {}).get("matched_skills", []) or []
            missing_skills = block_scores.get("block_b", {}).get("missing_skills", []) or []
            tech_stack = block_scores.get("block_a", {}).get("tech_stack", []) or []
            salary_range = block_scores.get("block_d", {}).get("salary_range")
            seniority = block_scores.get("block_a", {}).get("seniority_level")

        if "eval_ghost" in row_keys and row["eval_ghost"] is not None:
            is_ghost = bool(row["eval_ghost"])
        elif "is_ghost_job" in row_keys and row["is_ghost_job"] is not None:
            is_ghost = bool(row["is_ghost_job"])

        if "eval_auth" in row_keys and row["eval_auth"] is not None:
            auth_block = bool(row["eval_auth"])
        elif "work_auth_blocker" in row_keys and row["work_auth_blocker"] is not None:
            auth_block = bool(row["work_auth_blocker"])

        if "eval_reason" in row_keys and row["eval_reason"]:
            eval_reason = row["eval_reason"]
        elif "reason" in row_keys and row["reason"]:
            eval_reason = row["reason"]

        title_str = row["title"] or ""
        desc_str = row["description"] or ""

        # Fallback quick tech extraction and seniority if not evaluated yet
        if not tech_stack:
            tech_stack = extract_quick_keywords(f"{title_str} {desc_str}")
        if not matched_skills and tech_stack:
            matched_skills = tech_stack[:3]
        if not seniority:
            seniority = extract_quick_seniority(title_str)

        return JobPosting(
            id=row["id"],
            company=row["company"],
            title=row["title"],
            url=row["url"],
            portal_type=row["portal_type"] or "generic",
            source=row["source"] or "scanner",
            status=status,
            location=row["location"],
            description=row["description"],
            h1b_sponsored=h1b,
            posted_at=posted_at_val,
            discovered_at=_parse_dt(row["discovered_at"]) or datetime.utcnow(),
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
            raw_data=_load_json(row["raw_data"], default=None),
            fit_score=fit_score,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            tech_stack=tech_stack,
            salary_range=salary_range,
            seniority=seniority,
            is_ghost_job=is_ghost,
            work_auth_blocker=auth_block,
            evaluation_reason=eval_reason,
        )


class EvaluationRepository(BaseRepository):
    """Repository managing Stage 2 evaluation results."""

    def insert_evaluation(self, evaluation: EvaluationResult) -> EvaluationResult:
        """Insert or replace an evaluation result."""
        if not evaluation.id:
            evaluation.id = f"eval_{evaluation.job_id or uuid.uuid4().hex[:8]}"

        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evaluations (
                    id, job_id, fit_score, score, reason, block_scores,
                    work_auth_blocker, is_ghost_job, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    evaluation.id,
                    evaluation.job_id,
                    evaluation.fit_score,
                    evaluation.score,
                    evaluation.reason,
                    _dump_json(evaluation.block_scores),
                    1 if evaluation.work_auth_blocker else 0,
                    1 if evaluation.is_ghost_job else 0,
                    _format_dt(evaluation.evaluated_at) or datetime.utcnow().isoformat(),
                ),
            )
        return evaluation

    def get_by_job_id(self, job_id: str) -> Optional[EvaluationResult]:
        """Fetch the latest evaluation result for a given job."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM evaluations WHERE job_id = ? ORDER BY evaluated_at DESC LIMIT 1;",
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_eval(row)

    def get_evaluation(self, evaluation_id: str) -> Optional[EvaluationResult]:
        """Fetch evaluation result by its ID."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM evaluations WHERE id = ?;", (evaluation_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_eval(row)

    def list_evaluations(self, limit: Optional[int] = None) -> List[EvaluationResult]:
        """List evaluations ordered by evaluated_at descending."""
        query = "SELECT * FROM evaluations ORDER BY evaluated_at DESC"
        params: List[Any] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self.connection() as conn:
            cursor = conn.execute(query, tuple(params))
            return [self._row_to_eval(r) for r in cursor.fetchall()]

    @staticmethod
    def _row_to_eval(row: sqlite3.Row) -> EvaluationResult:
        """Convert a sqlite row to an EvaluationResult model."""
        return EvaluationResult(
            id=row["id"],
            job_id=row["job_id"],
            fit_score=float(row["fit_score"]),
            score=float(row["score"]) if row["score"] is not None else float(row["fit_score"]),
            reason=row["reason"],
            block_scores=_load_json(row["block_scores"], default={}),
            work_auth_blocker=bool(row["work_auth_blocker"]),
            is_ghost_job=bool(row["is_ghost_job"]),
            evaluated_at=_parse_dt(row["evaluated_at"]) or datetime.utcnow(),
        )


class ArtifactRepository(BaseRepository):
    """Repository managing Stage 3 tailored artifacts."""

    def insert_artifacts(self, artifacts: TailoredArtifacts) -> TailoredArtifacts:
        """Insert or replace tailored artifacts."""
        if not artifacts.id:
            artifacts.id = f"art_{artifacts.job_id or uuid.uuid4().hex[:8]}"

        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO artifacts (
                    id, job_id, resume_pdf_path, resume_json_path, cover_letter_path,
                    qa_answers, linkedin_outreach, tailored_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    artifacts.id,
                    artifacts.job_id,
                    artifacts.resume_pdf_path,
                    artifacts.resume_json_path,
                    artifacts.cover_letter_path,
                    _dump_json(artifacts.qa_answers),
                    artifacts.linkedin_outreach,
                    _format_dt(artifacts.tailored_at) or datetime.utcnow().isoformat(),
                ),
            )
        return artifacts

    def get_by_job_id(self, job_id: str) -> Optional[TailoredArtifacts]:
        """Fetch the latest tailored artifacts for a given job."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE job_id = ? ORDER BY tailored_at DESC LIMIT 1;",
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_artifact(row)

    def get_artifacts(self, artifact_id: str) -> Optional[TailoredArtifacts]:
        """Fetch tailored artifacts by ID."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM artifacts WHERE id = ?;", (artifact_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_artifact(row)

    @staticmethod
    def _row_to_artifact(row: sqlite3.Row) -> TailoredArtifacts:
        """Convert a sqlite row to a TailoredArtifacts model."""
        return TailoredArtifacts(
            id=row["id"],
            job_id=row["job_id"],
            resume_pdf_path=row["resume_pdf_path"],
            resume_json_path=row["resume_json_path"],
            cover_letter_path=row["cover_letter_path"],
            qa_answers=_load_json(row["qa_answers"], default={}),
            linkedin_outreach=row["linkedin_outreach"],
            tailored_at=_parse_dt(row["tailored_at"]) or datetime.utcnow(),
        )


class ApplicationRepository(BaseRepository):
    """Repository managing Stage 5 application lifecycle records."""

    def insert_application(self, application: ApplicationRecord) -> ApplicationRecord:
        """Insert or replace an application record."""
        if not application.id:
            application.id = f"app_{application.job_id or uuid.uuid4().hex[:8]}"

        status_val = (
            application.status.value
            if isinstance(application.status, JobStatus)
            else str(application.status)
        )

        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO applications (
                    id, job_id, company, title, status, applied_at,
                    portal_url, resume_pdf_path, submission_receipt_id,
                    followup_due_date, last_status_update, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    application.id,
                    application.job_id,
                    application.company,
                    application.title,
                    status_val,
                    _format_dt(application.applied_at) or datetime.utcnow().isoformat(),
                    application.portal_url,
                    application.resume_pdf_path,
                    application.submission_receipt_id,
                    _format_dt(application.followup_due_date),
                    _format_dt(application.last_status_update),
                    application.notes,
                ),
            )
        return application

    def get_application(self, application_id: str) -> Optional[ApplicationRecord]:
        """Fetch an application record by ID."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM applications WHERE id = ?;", (application_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_app(row)

    def get_by_job_id(self, job_id: str) -> Optional[ApplicationRecord]:
        """Fetch the application record for a given job."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM applications WHERE job_id = ? ORDER BY applied_at DESC LIMIT 1;",
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_app(row)

    def update_stage(
        self,
        application_id: str,
        status: Union[JobStatus, str],
        notes: Optional[str] = None,
        followup_due_date: Optional[datetime] = None,
    ) -> bool:
        """Update application stage, status, followup due date, and notes."""
        status_val = status.value if isinstance(status, JobStatus) else str(status)
        now_str = datetime.utcnow().isoformat()

        query = "UPDATE applications SET status = ?, last_status_update = ?"
        params: List[Any] = [status_val, now_str]

        if notes is not None:
            query += ", notes = ?"
            params.append(notes)

        if followup_due_date is not None:
            query += ", followup_due_date = ?"
            params.append(_format_dt(followup_due_date))

        query += " WHERE id = ?;"
        params.append(application_id)

        with self.connection() as conn:
            cursor = conn.execute(query, tuple(params))
            return cursor.rowcount > 0

    def update_status(
        self,
        application_id: str,
        status: Union[JobStatus, str],
        notes: Optional[str] = None,
    ) -> bool:
        """Alias for update_stage matching JobRepository interface."""
        return self.update_stage(application_id=application_id, status=status, notes=notes)

    def get_active_applications(self) -> List[ApplicationRecord]:
        """Fetch all active applications (excluding rejected, ghost_job, ignored, failed)."""
        inactive_statuses = [
            JobStatus.REJECTED.value,
            JobStatus.GHOST_JOB.value,
            JobStatus.IGNORED.value,
            JobStatus.FAILED.value,
        ]
        placeholders = ",".join("?" for _ in inactive_statuses)
        query = f"SELECT * FROM applications WHERE status NOT IN ({placeholders}) ORDER BY applied_at DESC;"

        with self.connection() as conn:
            cursor = conn.execute(query, tuple(inactive_statuses))
            return [self._row_to_app(r) for r in cursor.fetchall()]

    def list_applications(self, limit: Optional[int] = None) -> List[ApplicationRecord]:
        """List all application records ordered by applied_at descending."""
        query = "SELECT * FROM applications ORDER BY applied_at DESC"
        params: List[Any] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self.connection() as conn:
            cursor = conn.execute(query, tuple(params))
            return [self._row_to_app(r) for r in cursor.fetchall()]

    @staticmethod
    def _row_to_app(row: sqlite3.Row) -> ApplicationRecord:
        """Convert a sqlite row to an ApplicationRecord model."""
        status_str = row["status"]
        try:
            status = JobStatus(status_str)
        except ValueError:
            status = JobStatus.APPLIED

        return ApplicationRecord(
            id=row["id"],
            job_id=row["job_id"],
            company=row["company"],
            title=row["title"],
            status=status,
            applied_at=_parse_dt(row["applied_at"]) or datetime.utcnow(),
            portal_url=row["portal_url"],
            resume_pdf_path=row["resume_pdf_path"],
            submission_receipt_id=row["submission_receipt_id"],
            followup_due_date=_parse_dt(row["followup_due_date"]),
            last_status_update=_parse_dt(row["last_status_update"]),
            notes=row["notes"],
        )


class WorkdayProfileRepository(BaseRepository):
    """Repository for managing candidate Workday enterprise autofill profile."""

    def __init__(self, db_path: str = "./data/careergraph.db"):
        super().__init__(db_path)
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workday_profiles (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    email TEXT,
                    password TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT,
                    phone_device_type TEXT,
                    address_line1 TEXT,
                    city TEXT,
                    state TEXT,
                    postal_code TEXT,
                    country TEXT,
                    is_authorized_us INTEGER,
                    needs_sponsorship_future INTEGER,
                    previously_employed INTEGER,
                    veteran_status TEXT,
                    disability_status TEXT,
                    gender TEXT,
                    race_ethnicity TEXT,
                    source_heard_about TEXT,
                    updated_at TEXT
                );
                """
            )

    def get_profile(self) -> Dict[str, Any]:
        """Fetch saved Workday profile or return defaults."""
        from src.core.persona import (
            SAMPLE_EMAIL,
            SAMPLE_FIRST_NAME,
            SAMPLE_LAST_NAME,
            SAMPLE_PHONE,
        )
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM workday_profiles WHERE id = 1;")
            row = cursor.fetchone()
            if not row:
                return {
                    "email": SAMPLE_EMAIL,
                    "password": "CareerGraph#2026Secure!",
                    "first_name": SAMPLE_FIRST_NAME,
                    "last_name": SAMPLE_LAST_NAME,
                    "phone": SAMPLE_PHONE,
                    "phone_device_type": "Mobile",
                    "address_line1": "123 Innovation Way",
                    "city": "Seattle",
                    "state": "WA",
                    "postal_code": "98101",
                    "country": "United States of America",
                    "is_authorized_us": True,
                    "needs_sponsorship_future": False,
                    "previously_employed": False,
                    "veteran_status": "not_veteran",
                    "disability_status": "no_disability",
                    "gender": "Decline to state",
                    "race_ethnicity": "Decline to state",
                    "source_heard_about": "Company Website",
                }
            return {
                "email": row["email"],
                "password": row["password"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "phone": row["phone"],
                "phone_device_type": row["phone_device_type"],
                "address_line1": row["address_line1"],
                "city": row["city"],
                "state": row["state"],
                "postal_code": row["postal_code"],
                "country": row["country"],
                "is_authorized_us": bool(row["is_authorized_us"]),
                "needs_sponsorship_future": bool(row["needs_sponsorship_future"]),
                "previously_employed": bool(row["previously_employed"]),
                "veteran_status": row["veteran_status"],
                "disability_status": row["disability_status"],
                "gender": row["gender"],
                "race_ethnicity": row["race_ethnicity"],
                "source_heard_about": row["source_heard_about"],
            }

    def save_profile(self, profile: Dict[str, Any]) -> None:
        """Upsert Workday profile details."""
        now_str = datetime.utcnow().isoformat()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workday_profiles (
                    id, email, password, first_name, last_name, phone, phone_device_type,
                    address_line1, city, state, postal_code, country,
                    is_authorized_us, needs_sponsorship_future, previously_employed,
                    veteran_status, disability_status, gender, race_ethnicity,
                    source_heard_about, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    profile.get("email", ""),
                    profile.get("password", ""),
                    profile.get("first_name", ""),
                    profile.get("last_name", ""),
                    profile.get("phone", ""),
                    profile.get("phone_device_type", "Mobile"),
                    profile.get("address_line1", ""),
                    profile.get("city", ""),
                    profile.get("state", ""),
                    profile.get("postal_code", ""),
                    profile.get("country", "United States of America"),
                    1 if profile.get("is_authorized_us", True) else 0,
                    1 if profile.get("needs_sponsorship_future", True) else 0,
                    1 if profile.get("previously_employed", False) else 0,
                    profile.get("veteran_status", "not_veteran"),
                    profile.get("disability_status", "no_disability"),
                    profile.get("gender", "Male"),
                    profile.get("race_ethnicity", "Asian"),
                    profile.get("source_heard_about", "LinkedIn"),
                    now_str,
                ),
            )

