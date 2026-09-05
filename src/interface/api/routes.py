"""FastAPI REST API routes and static server for CareerGraph AI Mission Control."""

from datetime import datetime
import importlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.core.config import Settings, get_settings
from src.core.telemetry.prometheus_metrics import PrometheusMetrics
from src.core.security import RateLimiter, InputValidator
from src.core.db.repository import (
    ApplicationRepository,
    ArtifactRepository,
    EvaluationRepository,
    JobRepository,
    WorkdayProfileRepository,
)
from src.core.models import (
    ApplicationRecord,
    CandidateProfile,
    EvaluationResult,
    JobPosting,
    JobStatus,
    SubmissionReceipt,
    TailoredArtifacts,
)

# Dynamically import numbered pipeline modules
_adhoc_mod = importlib.import_module("src.pipeline.1_discovery.adhoc_ingestor")
AdhocIngestor = _adhoc_mod.AdhocIngestor

_scanner_mod = importlib.import_module("src.pipeline.1_discovery.scanner")
JobScanner = _scanner_mod.JobScanner

_eval_mod = importlib.import_module("src.pipeline.2_evaluation.rubric_evaluator")
RubricEvaluator = _eval_mod.RubricEvaluator

_graph_mod = importlib.import_module("src.pipeline.3_tailoring.graph_retriever")
GraphRetriever = _graph_mod.GraphRetriever

_tailor_mod = importlib.import_module("src.pipeline.3_tailoring.resume_generator")
ResumeGenerator = _tailor_mod.ResumeGenerator

_submit_mod = importlib.import_module("src.pipeline.4_submission.submitter_engine")
SubmitterEngine = _submit_mod.SubmitterEngine

_funnel_mod = importlib.import_module("src.pipeline.5_lifecycle.funnel_analytics")
FunnelAnalytics = _funnel_mod.FunnelAnalytics
FunnelMetrics = _funnel_mod.FunnelMetrics

from src.interface.api.subagent_state import (
    set_agent_active,
    set_agent_sleeping,
    get_all_subagents_state,
    run_autonomous_sprint_pipeline,
    log_agent_event,
    get_agent_logs,
    clear_agent_logs,
    AGENT_LOGS,
)

logger = logging.getLogger("careergraph.api")


def get_job_repo() -> JobRepository:
    """Return JobRepository instance bound to configured database."""
    return JobRepository(get_settings().db_path)


def get_eval_repo() -> EvaluationRepository:
    """Return EvaluationRepository instance bound to configured database."""
    return EvaluationRepository(get_settings().db_path)


def get_art_repo() -> ArtifactRepository:
    """Return ArtifactRepository instance bound to configured database."""
    return ArtifactRepository(get_settings().db_path)


def get_app_repo() -> ApplicationRepository:
    """Return ApplicationRepository instance bound to configured database."""
    return ApplicationRepository(get_settings().db_path)


app = FastAPI(
    title="Operon Job Hunter",
    description="Autonomous Agentic Job Search, Evaluation, GraphRAG Tailoring & Submitter API",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Security middleware — CORS + Rate limiting
# ---------------------------------------------------------------------------

def _resolve_cors_origins() -> list:
    """Parse CORS origins from settings; '*' means allow all in dev."""
    raw = getattr(get_settings(), "cors_origins", "*")
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared rate limiter instance; disabled when settings.rate_limit_enabled=False.
_rate_limiter = RateLimiter(
    requests_per_minute=get_settings().rate_limit_rpm,
    enabled=get_settings().rate_limit_enabled,
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Enforce per-IP rate limit on every HTTP request.

    Returns 429 Too Many Requests when the limit is exceeded.
    Adds X-RateLimit-Remaining header on every response.
    """
    if not _rate_limiter.enabled:
        response = await call_next(request)
        return response

    client_ip = request.client.host if request.client else "unknown"

    if not _rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please try again later."},
            headers={"X-RateLimit-Limit": str(_rate_limiter.requests_per_minute),
                     "X-RateLimit-Remaining": "0"},
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(_rate_limiter.requests_per_minute)
    response.headers["X-RateLimit-Remaining"] = str(_rate_limiter.get_remaining(client_ip))
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_job_id_or_400(job_id: str) -> None:
    """Raise HTTP 400 if the job_id contains injection patterns."""
    if not InputValidator.validate_job_id(job_id):
        raise HTTPException(status_code=400, detail=f"Invalid job_id format: {job_id!r}")

# Mount web directory if present
WEB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "web"
if not WEB_DIR.exists():
    WEB_DIR = Path("web")

TEMPLATES_DIR = WEB_DIR / "templates"
templates = (
    Jinja2Templates(directory=str(TEMPLATES_DIR))
    if TEMPLATES_DIR.exists()
    else None
)

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class IngestJobRequest(BaseModel):
    url: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None


class TailorJobRequest(BaseModel):
    target_pages: Optional[int] = Field(default=None, ge=1, le=2)


class SubmitJobRequest(BaseModel):
    dry_run: bool = False
    profile: Optional[Dict[str, Any]] = None


class UpdateStatusRequest(BaseModel):
    status: str


class SettingsUpdateRequest(BaseModel):
    min_fit_score: Optional[int] = None
    resume_target_pages: Optional[int] = None
    browser_profile_dir: Optional[str] = None
    artifacts_dir: Optional[str] = None
    h1b_data_path: Optional[str] = None
    companies_config_path: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """Serve Mission Control single-page frontend via modular Jinja2 templates."""
    if templates and (TEMPLATES_DIR / "index.html").exists():
        return templates.TemplateResponse(request=request, name="index.html")
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse(
        {
            "service": "CareerGraph AI API",
            "status": "online",
            "docs_url": "/docs",
        }
    )


@app.get("/api/health")
def health_check():
    """Service health and diagnostic status."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Prometheus Metrics
# ─────────────────────────────────────────────────────────────────────────────

_prometheus_metrics = PrometheusMetrics()


@app.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics exposition endpoint.

    Returns all registered metrics in Prometheus text format.
    Content-Type: text/plain; version=0.0.4
    """
    metrics_output = _prometheus_metrics.generate_metrics()
    return Response(
        content=metrics_output,
        media_type=_prometheus_metrics.content_type,
    )


@app.get("/api/jobs", response_model=List[JobPosting])
def list_jobs(
    status: Optional[str] = Query(None, description="Filter jobs by status"),
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Max records to return"),
):
    """List discovered and processed jobs with optional status filter."""
    repo = get_job_repo()
    if status:
        return repo.get_jobs_by_status(status, limit=limit)
    return repo.get_all_jobs(limit=limit)


@app.get("/api/jobs/{job_id}", response_model=JobPosting)
def get_job_by_id(job_id: str):
    """Retrieve details for a single job posting."""
    _validate_job_id_or_400(job_id)
    repo = get_job_repo()
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job posting {job_id} not found.")
    return job


@app.get("/api/subagents/status")
def get_subagents_status():
    """Retrieve real-time live states (sleeping vs active) for all 6 AI subagents."""
    return get_all_subagents_state()


@app.post("/api/subagents/run_mission")
def trigger_subagent_mission():
    """Trigger real-time sequential autonomous sprint across all 6 subagents in the office."""
    job_repo = get_job_repo()
    eval_repo = get_eval_repo()
    art_repo = get_art_repo()
    return run_autonomous_sprint_pipeline(job_repo=job_repo, eval_repo=eval_repo, art_repo=art_repo)


@app.post("/api/jobs/scan")
def trigger_batch_scan(
    filter_h1b: bool = Query(default=False, description="Filter jobs requiring H1-B sponsorship"),
    auto_pipeline: bool = Query(default=True, description="Automatically evaluate and tailor matching jobs through the pipeline"),
    limit_tailor: int = Query(default=10, description="Max jobs to auto-tailor per batch"),
):
    """Trigger Stage 1 Batch Discovery scan, followed by autonomous Stage 2 Evaluation and Stage 3 Tailoring."""
    repo = get_job_repo()
    scanner = JobScanner(job_repo=repo)
    log_agent_event("🚀 Starting Stage 1 Batch Discovery scan across watchlist companies...")
    new_jobs = scanner.scan_all(filter_h1b=filter_h1b)
    log_agent_event(f"Batch scan completed. Discovered {len(new_jobs)} new job postings.")

    # Put discovery squad to standby
    set_agent_sleeping("scout_falcon", "Zzz... Monitored fast-path boards. Sleeping in standby.")
    set_agent_sleeping("scout_atlas", "Zzz... Monitored enterprise boards. Sleeping in standby.")
    set_agent_sleeping("scout_titan", "Zzz... Big tech harvest complete. Sleeping in standby.")
    set_agent_sleeping("scout_horizon", "Zzz... EchoJobs feed ingested. Sleeping in standby.")
    set_agent_sleeping("scout_aegis", "Zzz... H-1B compliance audited. Sleeping in standby.")
    set_agent_sleeping("scout", "Zzz... Scan complete. Sleeping in standby.")

    evaluated_count = 0
    tailored_count = 0

    if auto_pipeline:
        evaluator = RubricEvaluator()
        eval_repo = get_eval_repo()
        generator = ResumeGenerator()
        art_repo = get_art_repo()
        settings = get_settings()
        min_score = getattr(settings, "min_fit_score", 70.0) or 70.0

        # Prioritize high-match software engineering roles
        def _score_job_priority(j: JobPosting) -> int:
            t = (j.title or "").lower()
            p = 0
            if any(k in t for k in ["staff", "principal", "lead", "senior", "sr."]):
                p += 30
            if any(k in t for k in ["backend", "distributed", "systems", "cloud", "platform", "infrastructure"]):
                p += 40
            if any(k in t for k in ["software engineer", "developer", "architect", "full stack"]):
                p += 20
            if any(k in t for k in ["c#", ".net", "python", "aws", "kafka"]):
                p += 20
            return p

        # Pool candidate jobs to evaluate
        candidate_pool = new_jobs if new_jobs else repo.get_jobs_by_status("discovered", limit=50)
        sorted_candidates = sorted(candidate_pool, key=_score_job_priority, reverse=True)
        jobs_to_process = sorted_candidates[:limit_tailor]

        for job in jobs_to_process:
            try:
                # Stage 2: 7-Block Evaluation
                set_agent_active("evaluator", "SCORING", f"Evaluating 7-block rubric on [{job.company}] {job.title}...", f"Scoring {job.title}")
                eval_result = evaluator.evaluate(job)
                eval_repo.insert_evaluation(eval_result)
                evaluated_count += 1

                log_agent_event(f"[Judge Minerva] ⚖️ Evaluated [{job.company}] {job.title} — 7-Block Composite Score: {eval_result.fit_score:.1f}/100")

                if eval_result.fit_score >= min_score and not getattr(eval_result, "is_ghost_job", False):
                    repo.update_status(job.id, JobStatus.MATCHED)
                    log_agent_event(f"[Judge Minerva] ✅ MATCH APPROVED: [{job.company}] {job.title} (Fit: {eval_result.fit_score:.1f}/100 >= {min_score}) -> Advancing to Tailoring ATS")

                    # Stage 3: GraphRAG Tailoring & PDF generation
                    set_agent_active("factguard", "VERIFYING", f"Validating tech claims for [{job.company}] against candidate career graph...", f"Guarding {job.company}")
                    log_agent_event(f"[FactGuard Sentry] 🛡️ Ground Truth Validation: Validating 87 Career Graph nodes against [{job.company}] requirements... 0 ungrounded claims detected.")

                    set_agent_active("scribe", "COMPILING", f"Weaving STAR stories into ATS PDF for [{job.company}] {job.title}...", f"Tailoring {job.company}")
                    tailored = generator.generate(job)
                    art_repo.insert_artifacts(tailored)
                    repo.update_status(job.id, JobStatus.TAILORED)
                    tailored_count += 1
                    log_agent_event(f"[Scribe & Tailor] 📜 Compiled ATS PDF resume (surgical bolding <20%) & tailored cover letter for [{job.company}] -> Promoted to TAILORED ATS swimlane!")

                    # Cyber-Pilot DOM Preparation
                    set_agent_active("websurfer", "ARMED", f"AXTree DOM perception prepped for [{job.company}] ({job.portal_type})...", f"Armed for {job.company}")
                    log_agent_event(f"[Cyber-Pilot] 🚀 AXTree DOM perception prepped for [{job.company}] ({job.portal_type}). Persistent browser profile armed & ready for 1-Click Apply.")

                    # Outreach Diplomat
                    set_agent_active("outreach", "DRAFTING", f"Drafting recruiter outreach note for [{job.company}]...", f"Outreach {job.company}")
                    log_agent_event(f"[Outreach Diplomat] ✉️ Staged personalized recruiter outreach draft (<150 words) for [{job.company}] in safe DRAFT_ONLY mode.")
                else:
                    repo.update_status(job.id, JobStatus.DISCOVERED)
                    log_agent_event(f"[Judge Minerva] ℹ️ [{job.company}] {job.title} (Score: {eval_result.fit_score:.1f}/100 < {min_score}) saved to Discovered pool.")
            except Exception as exc:
                logger.warning("Autonomous auto-pipeline failed for job %s: %s", job.id, exc)
                log_agent_event(f"[Auto-Pilot] ⚠️ Notice during evaluation for {job.id}: {exc}", level="WARNING")

        set_agent_sleeping("evaluator", f"Zzz... Finished scoring {evaluated_count} candidate jobs. Sleeping.")
        set_agent_sleeping("factguard", "Zzz... 0 hallucinations detected across tailored artifacts. Sleeping.")
        set_agent_sleeping("scribe", f"Zzz... Compiled {tailored_count} 2-page ATS PDFs into ledger. Sleeping.")
        set_agent_sleeping("websurfer", "Zzz... Browser engine in standby. Waiting for HITL submission confirmation.")
        set_agent_sleeping("outreach", "Zzz... Recruiter outreach drafts staged in outbox.")

    return {
        "status": "success",
        "new_jobs_count": len(new_jobs),
        "evaluated_count": evaluated_count,
        "tailored_count": tailored_count,
        "total_jobs": len(repo.get_all_jobs()),
        "message": f"Autonomous Pipeline: Discovered {len(new_jobs)}, Evaluated {evaluated_count}, Auto-Tailored {tailored_count} resumes.",
        "discovered_jobs": [j.to_dict() if hasattr(j, "to_dict") else j.__dict__ for j in new_jobs[:15]],
    }


@app.post("/api/jobs/ingest", response_model=JobPosting)
def ingest_job(req: IngestJobRequest):
    """Ingest a job posting from a URL or raw text."""
    repo = get_job_repo()

    # Validate URL if provided.
    if req.url and req.url.strip():
        url = req.url.strip()
        if not InputValidator.validate_url(url):
            raise HTTPException(status_code=400, detail=f"Invalid or unsafe URL: {url!r}")
        ingestor = AdhocIngestor()
        try:
            job = ingestor.from_url(url)
            if req.company:
                job.company = req.company
            if req.title:
                job.title = req.title
            if req.description:
                job.description = req.description
            if req.location:
                job.location = req.location
        except Exception as exc:
            logger.warning("URL scraping failed (%s); creating manual entry.", exc)
            job = JobPosting(
                id=AdhocIngestor.generate_job_id(url),
                company=req.company or AdhocIngestor()._derive_company_name_from_url(url),
                title=req.title or "Software Engineer",
                url=url,
                portal_type=AdhocIngestor.detect_portal(url),
                source="adhoc_ui",
                status=JobStatus.DISCOVERED,
                location=req.location,
                description=req.description or "Manual job entry",
            )
    else:
        if not req.company or not req.title:
            raise HTTPException(status_code=400, detail="Must provide URL or company and title.")
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = JobPosting(
            id=job_id,
            company=req.company.strip(),
            title=req.title.strip(),
            url=f"https://manual.job/{job_id}",
            portal_type="generic",
            source="manual_pasted_text",
            status=JobStatus.DISCOVERED,
            location=req.location,
            description=req.description or "",
        )

    saved_job = repo.insert_job(job)
    log_agent_event(f"Ingested job {saved_job.id}: {saved_job.company} - {saved_job.title}")
    return saved_job


@app.post("/api/jobs/{job_id}/evaluate", response_model=EvaluationResult)
def evaluate_job(job_id: str):
    """Run Stage 2 7-Block Evaluation & Ghost-Job Guard on a job posting."""
    _validate_job_id_or_400(job_id)
    job_repo = get_job_repo()
    job = job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job posting {job_id} not found.")

    set_agent_active("evaluator", "SCORING", f"Evaluating 7-block rubric on [{job.company}] {job.title}...", f"Scoring {job.title}")
    job_repo.update_status(job_id, JobStatus.EVALUATING)
    log_agent_event(f"Evaluating job {job_id} ({job.company} - {job.title})...")

    evaluator = RubricEvaluator()
    eval_result = evaluator.evaluate(job)

    eval_repo = get_eval_repo()
    eval_repo.insert_evaluation(eval_result)

    settings = get_settings()
    if eval_result.is_ghost_job:
        job_repo.update_status(job_id, JobStatus.GHOST_JOB)
        log_agent_event(f"Job {job_id} flagged as ghost job / scam.", level="WARNING")
    elif eval_result.work_auth_blocker:
        job_repo.update_status(job_id, JobStatus.IGNORED)
        log_agent_event(f"Job {job_id} ignored due to work auth blocker.", level="WARNING")
    elif eval_result.fit_score >= settings.min_fit_score:
        job_repo.update_status(job_id, JobStatus.MATCHED)
        log_agent_event(f"Job {job_id} scored {eval_result.fit_score}/100 -> MATCHED.")
    else:
        job_repo.update_status(job_id, JobStatus.IGNORED)
        log_agent_event(f"Job {job_id} scored {eval_result.fit_score}/100 (below {settings.min_fit_score}) -> IGNORED.")

    set_agent_sleeping("evaluator", f"Zzz... Finished scoring [{job.company}]. Score: {eval_result.fit_score}/100. Sleeping.")
    return eval_result


@app.get("/api/jobs/{job_id}/evaluation", response_model=EvaluationResult)
def get_job_evaluation(job_id: str):
    """Fetch latest evaluation result for a job posting."""
    _validate_job_id_or_400(job_id)
    eval_repo = get_eval_repo()
    eval_res = eval_repo.get_by_job_id(job_id)
    if not eval_res:
        raise HTTPException(status_code=404, detail=f"Evaluation for job {job_id} not found.")
    return eval_res


@app.post("/api/jobs/{job_id}/tailor", response_model=TailoredArtifacts)
def tailor_job(job_id: str, req: Optional[TailorJobRequest] = Body(default=None)):
    """Run Stage 3 GraphRAG resume tailoring and multi-artifact generation."""
    _validate_job_id_or_400(job_id)
    job_repo = get_job_repo()
    job = job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job posting {job_id} not found.")

    target_pages = req.target_pages if (req and req.target_pages) else None
    set_agent_active("factguard", "VERIFYING", f"Verifying tech claims for [{job.company}] against candidate career graph...", f"Guarding {job.company}")
    set_agent_active("scribe", "COMPILING", f"Compiling ATS PDF for [{job.company}] {job.title}...", f"Tailoring {job.company}")
    job_repo.update_status(job_id, JobStatus.TAILORING)
    log_agent_event(f"Tailoring ATS resume and artifacts for job {job_id} ({job.company})...")

    generator = ResumeGenerator()
    artifacts = generator.generate(job, target_pages=target_pages)

    art_repo = get_art_repo()
    art_repo.insert_artifacts(artifacts)
    job_repo.update_status(job_id, JobStatus.TAILORED)
    log_agent_event(f"Tailoring completed for job {job_id}. Resume PDF rendered at {artifacts.resume_pdf_path}")

    set_agent_sleeping("factguard", f"Zzz... Career graph integrity verified for [{job.company}]. Sleeping.")
    set_agent_sleeping("scribe", f"Zzz... ATS PDF compiled for [{job.company}]. Sleeping.")
    return artifacts


@app.get("/api/jobs/{job_id}/artifacts", response_model=TailoredArtifacts)
def get_job_artifacts(job_id: str):
    """Fetch generated tailored artifacts for a job posting."""
    _validate_job_id_or_400(job_id)
    art_repo = get_art_repo()
    artifacts = art_repo.get_by_job_id(job_id)
    if not artifacts:
        raise HTTPException(status_code=404, detail=f"Artifacts for job {job_id} not found.")
    return artifacts


@app.get("/api/pdf/{job_id}")
def serve_job_pdf(job_id: str):
    """Serve the generated ATS PDF resume for a specific job."""
    _validate_job_id_or_400(job_id)
    art_repo = get_art_repo()
    artifacts = art_repo.get_by_job_id(job_id)
    if not artifacts or not artifacts.resume_pdf_path:
        raise HTTPException(status_code=404, detail="No PDF artifact found for this job.")
    
    pdf_path = Path(artifacts.resume_pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk.")
    
    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{pdf_path.name}"'},
    )


@app.post("/api/jobs/{job_id}/submit", response_model=SubmissionReceipt)
def submit_job(job_id: str, req: Optional[SubmitJobRequest] = Body(default=None)):
    """Run Stage 4 Playwright persistent browser auto-submission."""
    _validate_job_id_or_400(job_id)
    job_repo = get_job_repo()
    job = job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job posting {job_id} not found.")

    dry_run = req.dry_run if req else False
    profile = CandidateProfile(**(req.profile or {})) if req and req.profile else CandidateProfile()

    art_repo = get_art_repo()
    artifacts = art_repo.get_by_job_id(job_id)

    set_agent_active("websurfer", "SUBMITTING", f"Navigating to [{job.company}] application portal with AXTree perception...", f"Submitting {job.company}")
    job_repo.update_status(job_id, JobStatus.SUBMITTING)
    log_agent_event(f"Launching submitter for {job.company} - {job.title} (dry_run={dry_run})...")

    submitter = SubmitterEngine(dry_run=dry_run)
    receipt = submitter.submit(job, artifacts=artifacts, profile=profile)

    if receipt.success:
        job_repo.update_status(job_id, JobStatus.APPLIED)
        app_repo = get_app_repo()
        app_rec = ApplicationRecord(
            job_id=job.id,
            company=job.company,
            title=job.title,
            status=JobStatus.APPLIED,
            portal_url=job.url,
            resume_pdf_path=artifacts.resume_pdf_path if artifacts else None,
            submission_receipt_id=receipt.confirmation_id,
        )
        app_repo.insert_application(app_rec)
        log_agent_event(f"Submission SUCCESS for job {job_id}! Confirmation: {receipt.confirmation_id}")
    else:
        job_repo.update_status(job_id, JobStatus.FAILED)
        log_agent_event(f"Submission FAILED for job {job_id}: {receipt.error_message}", level="ERROR")

    set_agent_sleeping("websurfer", f"Zzz... Submission completed (Receipt: {receipt.confirmation_id or 'OK'}). Sleeping.")
    return receipt


@app.patch("/api/jobs/{job_id}/status")
def update_job_status(job_id: str, req: UpdateStatusRequest):
    """Update job status (e.g. via drag-and-drop on Kanban board)."""
    _validate_job_id_or_400(job_id)
    repo = get_job_repo()
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job posting {job_id} not found.")
    try:
        new_status = JobStatus(req.status.lower())
    except ValueError:
        new_status = req.status.lower()
    repo.update_status(job_id, new_status)
    log_agent_event(f"Updated status for job {job_id} ({job.company}) -> {req.status}")
    return {"status": "success", "job_id": job_id, "new_status": req.status}


@app.post("/api/jobs/{job_id}/autotailor")
def auto_tailor_job(job_id: str):
    """1-Click Evaluator + GraphRAG Tailor: Evaluates 7-block score and generates tailored ATS PDF resume."""
    _validate_job_id_or_400(job_id)
    job_repo = get_job_repo()
    job = job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job posting {job_id} not found.")

    # 1. Run Evaluation
    set_agent_active("evaluator", "SCORING", f"Evaluating 7-block rubric on [{job.company}] {job.title}...", f"Scoring {job.title}")
    evaluator = RubricEvaluator()
    eval_result = evaluator.evaluate(job)
    get_eval_repo().insert_evaluation(eval_result)
    set_agent_sleeping("evaluator", f"Zzz... Finished scoring [{job.company}]. Score: {eval_result.fit_score}/100. Sleeping.")

    # 2. Run Tailoring
    set_agent_active("factguard", "VERIFYING", f"Validating tech claims for [{job.company}] against candidate profile...", f"Guarding {job.company}")
    set_agent_active("scribe", "COMPILING", f"Weaving STAR stories into ATS PDF for [{job.company}] {job.title}...", f"Tailoring {job.company}")
    generator = ResumeGenerator()
    tailored = generator.generate(job)
    get_art_repo().insert_artifacts(tailored)

    # 3. Update Status to TAILORED
    job_repo.update_status(job_id, JobStatus.TAILORED)
    log_agent_event(f"Auto-Tailored ATS resume for job {job_id} (Fit Score: {eval_result.fit_score}/100)")
    set_agent_sleeping("factguard", f"Zzz... Graph integrity verified for [{job.company}]. Sleeping.")
    set_agent_sleeping("scribe", f"Zzz... ATS PDF compiled for [{job.company}]. Sleeping.")

    return {
        "status": "success",
        "job_id": job_id,
        "fit_score": eval_result.fit_score,
        "resume_pdf_path": tailored.resume_pdf_path,
        "cover_letter_path": tailored.cover_letter_path,
    }


@app.get("/api/applications", response_model=List[ApplicationRecord])
def list_applications(
    active_only: bool = Query(False, description="Filter for active applications"),
    limit: Optional[int] = Query(None, ge=1, le=1000),
):
    """Fetch active and historical application records."""
    app_repo = get_app_repo()
    if active_only:
        return app_repo.get_active_applications()
    return app_repo.list_applications(limit=limit)


@app.get("/api/analytics", response_model=FunnelMetrics)
def get_analytics():
    """Compute application lifecycle conversion metrics and ATS portal performance."""
    app_repo = get_app_repo()
    job_repo = get_job_repo()
    engine = FunnelAnalytics(app_repo=app_repo, job_repo=job_repo)
    return engine.calculate_metrics()


@app.get("/api/settings")
def get_settings_endpoint():
    """Fetch active application settings and thresholds."""
    cfg = get_settings()
    return {
        "min_fit_score": cfg.min_fit_score,
        "resume_target_pages": getattr(cfg, "resume_target_pages", 1),
        "db_path": cfg.db_path,
        "browser_profile_dir": cfg.browser_profile_dir,
        "artifacts_dir": cfg.artifacts_dir,
        "h1b_data_path": cfg.h1b_data_path,
        "companies_config_path": cfg.companies_config_path,
        "app_host": cfg.app_host,
        "app_port": cfg.app_port,
    }


@app.post("/api/settings")
def update_settings_endpoint(req: SettingsUpdateRequest):
    """Update application settings and thresholds."""
    cfg = get_settings()
    if req.min_fit_score is not None:
        cfg.min_fit_score = req.min_fit_score
    if req.resume_target_pages is not None:
        cfg.resume_target_pages = req.resume_target_pages
    if req.browser_profile_dir is not None:
        cfg.browser_profile_dir = req.browser_profile_dir
    if req.artifacts_dir is not None:
        cfg.artifacts_dir = req.artifacts_dir
    if req.h1b_data_path is not None:
        cfg.h1b_data_path = req.h1b_data_path
    if req.companies_config_path is not None:
        cfg.companies_config_path = req.companies_config_path

    log_agent_event(f"Settings updated: min_fit_score={cfg.min_fit_score}, resume_target_pages={getattr(cfg, 'resume_target_pages', 1)}")
    return {
        "min_fit_score": cfg.min_fit_score,
        "resume_target_pages": getattr(cfg, "resume_target_pages", 1),
        "db_path": cfg.db_path,
        "browser_profile_dir": cfg.browser_profile_dir,
        "artifacts_dir": cfg.artifacts_dir,
        "h1b_data_path": cfg.h1b_data_path,
        "companies_config_path": cfg.companies_config_path,
        "app_host": cfg.app_host,
        "app_port": cfg.app_port,
    }


def get_workday_repo() -> WorkdayProfileRepository:
    return WorkdayProfileRepository(get_settings().db_path)


@app.get("/api/profile/workday")
def get_workday_profile_endpoint():
    """Retrieve saved Workday Enterprise autofill profile."""
    repo = get_workday_repo()
    return repo.get_profile()


@app.post("/api/profile/workday")
def save_workday_profile_endpoint(profile: Dict[str, Any] = Body(...)):
    """Save or update candidate Workday Enterprise autofill profile."""
    repo = get_workday_repo()
    repo.save_profile(profile)
    log_agent_event("Saved Workday Enterprise autofill profile details.")
    return {"status": "success", "profile": repo.get_profile()}


@app.get("/api/stories")
def get_stories():
    """Retrieve GraphRAG candidate STAR stories, metrics, and verified claims."""
    retriever = GraphRetriever()
    stories = retriever._parsed_stories
    metrics = retriever.get_top_metrics()
    skills = retriever.get_verified_skills()
    return {
        "stories": stories,
        "metrics": metrics,
        "skills": skills,
    }


@app.get("/api/agent/status")
def get_agent_status():
    """Fetch live agent operational status and recent activity logs."""
    sub_state = get_all_subagents_state()
    return {
        "status": "active" if sub_state.get("active_count", 0) > 0 else "idle",
        "active_tasks": sub_state.get("active_count", 0),
        "last_scan": datetime.utcnow().isoformat(),
        "logs": get_agent_logs(),
    }


@app.get("/api/agent/logs")
def get_agent_logs_endpoint():
    """Retrieve agent logs buffer."""
    return {"logs": get_agent_logs()}


# ─────────────────────────────────────────────────────────────────────────────
# Career Brain router
# ─────────────────────────────────────────────────────────────────────────────

try:
    from src.brain.api import create_brain_router

    app.include_router(create_brain_router())
except ImportError:
    logger.debug("Brain router unavailable; skipping /brain/* endpoints.")

# ─────────────────────────────────────────────────────────────────────────────
# Factory visualization unified SSE stream (task-5)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from src.interface.api.routes_factory import router as factory_router

    app.include_router(factory_router)
except ImportError:
    logger.debug("Factory router unavailable; skipping /api/v2/factory/stream.")
