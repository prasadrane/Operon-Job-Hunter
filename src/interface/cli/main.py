"""CareerGraph AI Unified Command Line Interface (CLI).

Commands:
  run        Run end-to-end agentic LangGraph pipeline for a job
  scan       Run Stage 1 discovery scanner across company watchlist
  ingest     Ingest a single job posting URL or text
  evaluate   Run Stage 2 7-Block evaluation & fit scoring on a job
  tailor     Run Stage 3 GraphRAG resume tailoring & PDF generation
  submit     Run Stage 4 Playwright persistent browser auto-submission
  status     Display live pipeline summary and stats table
  daemon     Run scheduled background scanner & sync loop
  ui         Launch FastAPI server and open Mission Control Web UI
"""

import argparse
import importlib
import logging
import sys
import time
import webbrowser
from typing import List, Optional
import uvicorn

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.core.config import get_settings
from src.core.db.dual_engine import init_dual_database_pool
from src.core.db.repository import (
    ApplicationRepository,
    ArtifactRepository,
    EvaluationRepository,
    JobRepository,
)
from src.core.models import ApplicationRecord, CandidateProfile, JobPosting, JobStatus
from src.interface.bot.telegram_hitl import TelegramHITLManager
from src.pipeline.state_machine import build_careergraph_pipeline

# Dynamically import numbered pipeline stage modules
_adhoc_mod = importlib.import_module("src.pipeline.1_discovery.adhoc_ingestor")
AdhocIngestor = _adhoc_mod.AdhocIngestor

_scanner_mod = importlib.import_module("src.pipeline.1_discovery.scanner")
JobScanner = _scanner_mod.JobScanner

_eval_mod = importlib.import_module("src.pipeline.2_evaluation.rubric_evaluator")
RubricEvaluator = _eval_mod.RubricEvaluator

_tailor_mod = importlib.import_module("src.pipeline.3_tailoring.resume_generator")
ResumeGenerator = _tailor_mod.ResumeGenerator

_builder_mod = importlib.import_module("src.pipeline.3_tailoring.career_graph_builder")
CareerGraphBuilder = _builder_mod.CareerGraphBuilder

_submit_mod = importlib.import_module("src.pipeline.4_submission.submitter_engine")
SubmitterEngine = _submit_mod.SubmitterEngine

_fastpath_mod = importlib.import_module("src.pipeline.4_submission.fastpath_engine")
FastPathSubmitter = _fastpath_mod.FastPathSubmitter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("careergraph.cli")


def get_job_repo() -> JobRepository:
    return JobRepository(get_settings().db_path)


def get_eval_repo() -> EvaluationRepository:
    return EvaluationRepository(get_settings().db_path)


def get_art_repo() -> ArtifactRepository:
    return ArtifactRepository(get_settings().db_path)


def get_app_repo() -> ApplicationRepository:
    return ApplicationRepository(get_settings().db_path)


def cmd_status(args: argparse.Namespace) -> int:
    """Display summary table of all jobs in the pipeline."""
    job_repo = get_job_repo()
    app_repo = get_app_repo()

    all_jobs = job_repo.get_all_jobs()
    all_apps = app_repo.list_applications()

    status_counts = {}
    for j in all_jobs:
        st = j.status.value if isinstance(j.status, JobStatus) else str(j.status)
        status_counts[st] = status_counts.get(st, 0) + 1

    print("\n" + "=" * 60)
    print(" 🚀 CareerGraph AI — Pipeline Summary")
    print("=" * 60)
    print(f"Total Discovered Jobs:  {len(all_jobs)}")
    print(f"Total Applications Sent: {len(all_apps)}")
    print("-" * 60)
    print(" Status Breakdown:")
    for status_name, count in sorted(status_counts.items()):
        print(f"   • {status_name:<16}: {count}")

    print("-" * 60)
    print(" Recent 5 Jobs:")
    for job in all_jobs[:5]:
        st = job.status.value if isinstance(job.status, JobStatus) else str(job.status)
        print(f"   [{job.id}] {job.company} — {job.title} ({st})")
    print("=" * 60 + "\n")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Execute end-to-end agentic StateGraph pipeline for a job."""
    job_id = args.job_id.strip()
    auto_submit = getattr(args, "auto_submit", False)

    init_dual_database_pool()
    job_repo = get_job_repo()
    job = job_repo.get_job(job_id)

    company = job.company if job else "Target Company"
    title = job.title if job else "Target Role"
    url = job.url if job else ""
    portal_type = job.portal_type if job else "greenhouse"

    print(f"🚀 Running CareerGraph StateGraph pipeline for [{job_id}] {company} - {title}...")
    app = build_careergraph_pipeline()
    config = {"configurable": {"thread_id": job_id}}

    initial_state = {
        "job_id": job_id,
        "company": company,
        "title": title,
        "url": url,
        "portal_type": portal_type,
        "fit_score": 0.0,
        "current_stage": "DISCOVERED",
        "is_ghost_job": False,
        "work_auth_blocker": False,
        "resume_pdf_path": None,
        "cover_letter_path": None,
        "submission_receipt_id": None,
        "qa_answers": {},
        "audit_logs": [],
        "errors": [],
        "evaluator_critiques": [],
    }

    state = app.invoke(initial_state, config=config)
    print(f"   Current Stage: {state.get('current_stage')}")
    print(f"   Fit Score: {state.get('fit_score')}")

    if state.get("current_stage") == "READY_FOR_HITL":
        hitl_manager = TelegramHITLManager()
        locked = hitl_manager.acquire_submission_lock(job_id)
        if not locked:
            print("⚠️ Submission already in progress / locked by HITL manager.")
            return 0

        print(f"✅ Generated Tailored Resume: {state.get('resume_pdf_path')}")
        print("⏸️  Pipeline paused at READY_FOR_HITL (Human-in-the-loop).")

        if auto_submit:
            print("🤖 Proceeding with auto-submission via FastPathSubmitter...")
            final_state = app.invoke(None, config=config)
            print(f"✅ Pipeline Completed! Stage: {final_state.get('current_stage')}, Receipt: {final_state.get('submission_receipt_id')}")
            hitl_manager.release_lock(job_id)

    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    """Run discovery scanner on configured company watchlist."""
    job_repo = get_job_repo()
    scanner = JobScanner(job_repo=job_repo)
    print("🔍 Starting Stage 1 Discovery Scan across target watchlist...")
    discovered = scanner.scan_all(filter_h1b=not args.no_h1b)
    print(f"✅ Discovered {len(discovered)} new job(s) matching criteria.")
    for j in discovered:
        print(f"   + [{j.id}] {j.company} — {j.title} ({j.portal_type})")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingest a single job posting by URL."""
    url = args.url.strip()
    print(f"📥 Ingesting job URL: {url}")
    ingestor = AdhocIngestor()
    job = ingestor.from_url(url)
    repo = get_job_repo()
    saved = repo.insert_job(job)
    print(f"✅ Ingested: {saved.company} - {saved.title} (ID: {saved.id}, Portal: {saved.portal_type})")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate a job using 7-Block rubric."""
    job_id = args.job_id.strip()
    job_repo = get_job_repo()
    job = job_repo.get_job(job_id)
    if not job:
        print(f"❌ Error: Job ID '{job_id}' not found in database.", file=sys.stderr)
        return 1

    print(f"⚖️  Evaluating job [{job.id}] {job.company} - {job.title}...")
    evaluator = RubricEvaluator()
    res = evaluator.evaluate(job)

    eval_repo = get_eval_repo()
    eval_repo.insert_evaluation(res)

    settings = get_settings()
    if res.is_ghost_job:
        job_repo.update_status(job_id, JobStatus.GHOST_JOB)
    elif res.work_auth_blocker:
        job_repo.update_status(job_id, JobStatus.IGNORED)
    elif res.fit_score >= settings.min_fit_score:
        job_repo.update_status(job_id, JobStatus.MATCHED)
    else:
        job_repo.update_status(job_id, JobStatus.IGNORED)

    print(f"✅ Evaluation Complete!")
    print(f"   Score: {res.fit_score}/100")
    print(f"   Reason: {res.reason}")
    print(f"   Ghost Job: {res.is_ghost_job} | Work Auth Blocker: {res.work_auth_blocker}")
    return 0


def cmd_tailor(args: argparse.Namespace) -> int:
    """Generate tailored resume, cover letter, and Q&A."""
    job_id = args.job_id.strip()
    job_repo = get_job_repo()
    job = job_repo.get_job(job_id)
    if not job:
        print(f"❌ Error: Job ID '{job_id}' not found in database.", file=sys.stderr)
        return 1

    pages = args.pages if getattr(args, "pages", None) is not None else get_settings().resume_target_pages
    print(f"📝 Tailoring ATS Resume ({pages}-page) for [{job.id}] {job.company}...")
    generator = ResumeGenerator()
    artifacts = generator.generate(job, target_pages=pages)

    art_repo = get_art_repo()
    art_repo.insert_artifacts(artifacts)
    job_repo.update_status(job_id, JobStatus.TAILORED)

    print(f"✅ Tailoring Complete!")
    print(f"   Generated ATS Resume: {artifacts.resume_pdf_path}")
    print(f"   Cover Letter: {artifacts.cover_letter_path}")
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    """Submit job application via Playwright."""
    job_id = args.job_id.strip()
    dry_run = getattr(args, "dry_run", False)

    job_repo = get_job_repo()
    job = job_repo.get_job(job_id)
    if not job:
        print(f"❌ Error: Job ID '{job_id}' not found in database.", file=sys.stderr)
        return 1

    art_repo = get_art_repo()
    artifacts = art_repo.get_by_job_id(job_id)

    print(f"🤖 Launching Submitter for [{job.id}] {job.company} (dry_run={dry_run})...")
    submitter = SubmitterEngine(dry_run=dry_run)
    receipt = submitter.submit(job, artifacts=artifacts, profile=CandidateProfile())

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
        print(f"✅ Submission Success: {receipt.success}")
        print(f"   Confirmation ID: {receipt.confirmation_id}")
        if receipt.screenshot_path:
            print(f"   Screenshot: {receipt.screenshot_path}")
    else:
        job_repo.update_status(job_id, JobStatus.FAILED)
        print(f"❌ Submission Failed: {receipt.error_message}")
    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    """Run periodic background scanner and lifecycle daemon."""
    iterations = getattr(args, "iterations", None)
    interval = getattr(args, "interval", 300) or 300
    heal_interval = getattr(args, "heal_interval", 0) or 0
    print(f"🔄 Starting CareerGraph AI Daemon (interval={interval}s, max_iterations={iterations or 'unlimited'})...")
    if heal_interval > 0:
        print(f"   🩹 Self-healing every {heal_interval} iterations")

    scanner = JobScanner(job_repo=get_job_repo())

    # Lazy import for multi-stage healing orchestrator
    _orchestrator = None
    if heal_interval > 0:
        try:
            import importlib
            _healing_pkg = importlib.import_module("src.pipeline.5_lifecycle.healing")
            _orchestrator = _healing_pkg.build_default_orchestrator()
        except Exception as exc:
            logger.warning("Healing orchestrator unavailable: %s", exc)

    count = 0
    while True:
        count += 1
        print(f"\n[Daemon Iteration {count}] Running scan...")
        try:
            discovered = scanner.scan_all()
            print(f"   Discovered {len(discovered)} jobs.")
        except Exception as exc:
            logger.error("Daemon scan error: %s", exc)

        # Run multi-stage healing on schedule
        if _orchestrator and heal_interval > 0 and count % heal_interval == 0:
            try:
                reports = _orchestrator.run_cycle()
                total_fixed = sum(r.fixes_applied for r in reports.values())
                total_errors = sum(r.errors_detected for r in reports.values())
                if total_fixed > 0:
                    print(f"   🩹 Healing: {total_fixed} fixes across {len(reports)} stages")
                elif total_errors > 0:
                    print(f"   🩹 Healing: {total_errors} errors detected, no fixes available")
            except Exception as exc:
                logger.error("Daemon healing error: %s", exc)

        print(f"Daemon iteration {count} completed.")

        if iterations is not None and count >= iterations:
            print("Reached target iterations; daemon exiting.")
            break

        time.sleep(interval)

    return 0


def cmd_heal(args: argparse.Namespace) -> int:
    """Run multi-stage self-healing orchestrator."""
    dry_run = getattr(args, "dry_run", False)
    stage = getattr(args, "stage", None)
    show_status = getattr(args, "status", False)

    try:
        import importlib
        _healing_pkg = importlib.import_module("src.pipeline.5_lifecycle.healing")
        build_orchestrator = _healing_pkg.build_default_orchestrator

        orchestrator = build_orchestrator(dry_run=dry_run)

        if show_status:
            status = orchestrator.get_status()
            print(f"\n{'='*70}")
            print(f"  Healing System Status")
            print(f"{'='*70}")
            print(f"  Dry run:    {status['dry_run']}")
            print(f"  Since:      {status['since_hours']}h")
            err = status.get("error_stats", {})
            print(f"  Errors:     {err.get('total', 0)} total, {err.get('unresolved', 0)} unresolved")
            print(f"\n  Registered Healers:")
            for name, info in status["healers"].items():
                can_run = "✓ ready" if info["can_run"] else "⏸ cooldown"
                print(f"    {name:15s}  [{info['stage_label']:20s}]  {can_run}")
            print(f"{'='*70}")
            return 0

        print(f"🩹 Running multi-stage healing orchestrator...")
        if stage:
            print(f"   Target stage: {stage}")
        if dry_run:
            print(f"   (DRY RUN — no changes applied)")

        reports = orchestrator.run_cycle(stage=stage)

        print(f"\n{'='*70}")
        print(f"  Multi-Stage Healing Report")
        print(f"{'='*70}")

        total_errors = 0
        total_attempted = 0
        total_applied = 0

        for healer_name, report in reports.items():
            total_errors += report.errors_detected
            total_attempted += report.fixes_attempted
            total_applied += report.fixes_applied

            status_icon = "✓" if report.fixes_applied > 0 else "·"
            print(f"\n  {status_icon} {report.healer:15s}  errors={report.errors_detected}  attempted={report.fixes_attempted}  fixed={report.fixes_applied}")

            for result in report.results:
                mark = "✓" if result.success else "✗"
                print(f"      {mark} {result.action[:70]}")

        if not reports:
            print("\n  No errors detected across any stage.")

        print(f"\n{'─'*70}")
        print(f"  TOTALS:  {total_errors} errors  →  {total_attempted} attempted  →  {total_applied} fixed")
        print(f"{'='*70}")
        return 0

    except ImportError as exc:
        print(f"Healing orchestrator not available: {exc}")
        return 1
    except Exception as exc:
        print(f"Healing error: {exc}")
        logger.error("Healing error: %s", exc)
        return 1


def cmd_errors(args: argparse.Namespace) -> int:
    """Display structured error log from persistent storage."""
    unresolved_only = getattr(args, "unresolved", False)
    company = getattr(args, "company", None)
    source = getattr(args, "source", None)
    limit = getattr(args, "limit", 50) or 50

    try:
        import importlib
        _err_mod = importlib.import_module("src.core.db.error_log")
        repo = _err_mod.ErrorLogRepository()

        if unresolved_only:
            errors = repo.get_unresolved_errors(since_hours=168, limit=limit)  # last 7 days
        elif company:
            errors = repo.get_errors_by_company(company, limit=limit)
        elif source:
            errors = repo.get_recent_errors(limit=limit, source=source)
        else:
            errors = repo.get_recent_errors(limit=limit)

        stats = repo.get_error_stats()

        print(f"\n{'='*70}")
        print(f"  Error Log — {stats['total']} total, {stats['unresolved']} unresolved")
        print(f"{'='*70}")

        if stats.get("by_source"):
            print("\n  By source:")
            for src, cnt in stats["by_source"].items():
                print(f"    {src:20s} {cnt:>5d}")

        if stats.get("by_type"):
            print("\n  By error type:")
            for etype, cnt in list(stats["by_type"].items())[:8]:
                print(f"    {etype:20s} {cnt:>5d}")

        if stats.get("top_companies"):
            print("\n  Top failing companies:")
            for comp, cnt in list(stats["top_companies"].items())[:10]:
                print(f"    {comp:25s} {cnt:>5d} unresolved")

        if not errors:
            print(f"\n  No {'unresolved ' if unresolved_only else ''}errors found.")
        else:
            print(f"\n  Recent errors ({len(errors)}):")
            print(f"  {'─'*66}")
            for err in errors:
                resolved_mark = "✓" if err.resolved else "✗"
                ts = err.timestamp[:16].replace("T", " ")
                status = err.http_status or ""
                print(f"  {resolved_mark} {ts}  [{err.source:12s}] {err.component:25s} {err.error_type:15s} {status}")
                if err.message:
                    msg = err.message[:80]
                    print(f"    └─ {msg}")

        print(f"\n{'='*70}")
        return 0

    except ImportError as exc:
        print(f"Error log module not available: {exc}")
        return 1
    except Exception as exc:
        print(f"Error reading error log: {exc}")
        logger.error("Error log read error: %s", exc)
        return 1


def cmd_ui(args: argparse.Namespace) -> int:
    """Launch FastAPI server and open Mission Control Web UI."""
    host = getattr(args, "host", "0.0.0.0") or "0.0.0.0"
    port = getattr(args, "port", 8000) or 8000
    no_browser = getattr(args, "no_browser", False)

    url = f"http://localhost:{port}"
    print(f"🌐 Launching Operon Job Hunter Mission Control at {url}...")

    if not no_browser:
        try:
            webbrowser.open(url)
        except Exception as exc:
            logger.debug("Failed to open browser automatically: %s", exc)

    uvicorn.run("src.interface.api.routes_v2:app_v2", host=host, port=port, reload=False)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Career Brain CLI commands
# ─────────────────────────────────────────────────────────────────────────────


def cmd_brain_query(args: argparse.Namespace) -> int:
    """Query the Career Brain."""
    try:
        from src.brain.inference import BrainInference
    except ImportError as exc:
        print(f"Brain module not available: {exc}", file=sys.stderr)
        return 1

    query_text = args.query.strip()
    mode = getattr(args, "mode", "auto") or "auto"
    job_desc = getattr(args, "job_desc", None)

    print(f"🧠 Querying Career Brain (mode={mode})...")
    brain = BrainInference()
    response = brain.query(query_text, mode=mode, job_desc=job_desc)

    print(f"\nMode: {response.mode}")
    print(f"Confidence: {response.confidence:.2f}")
    print(f"Latency: {response.latency_ms:.0f}ms")
    print(f"\n{response.answer}")

    if response.warnings:
        print(f"\nWarnings: {response.warnings}")
    return 0


def cmd_brain_status(args: argparse.Namespace) -> int:
    """Check brain service status."""
    try:
        from src.brain.ollama_client import OllamaClient
    except ImportError as exc:
        print(f"Brain module not available: {exc}", file=sys.stderr)
        return 1

    client = OllamaClient()
    available = client.is_available()
    print(f"Ollama: {'✅ Available' if available else '❌ Not running'}")
    if available:
        models = client.list_models()
        print(f"Models: {', '.join(models) if models else 'None'}")
    return 0


def cmd_brain_models(args: argparse.Namespace) -> int:
    """List fine-tuned brain models."""
    try:
        from src.brain.model_registry import get_model_registry
    except ImportError as exc:
        print(f"Brain module not available: {exc}", file=sys.stderr)
        return 1

    registry = get_model_registry()
    models = registry.list_models()
    if not models:
        print("No models registered yet.")
        return 0

    for m in models:
        active = "✅" if m.get("active") else "  "
        print(f"{active} {m.get('version', '?')}: {m.get('model_name', '?')} ({m.get('base_model', '?')})")
    return 0


def cmd_brain(args: argparse.Namespace) -> int:
    """Dispatch brain subcommands."""
    brain_cmd = getattr(args, "brain_command", None)
    if not brain_cmd:
        print("Usage: careergraph brain {query|status|models}")
        return 1

    dispatch = {
        "query": cmd_brain_query,
        "status": cmd_brain_status,
        "models": cmd_brain_models,
    }
    handler = dispatch.get(brain_cmd)
    if handler:
        return handler(args)
    print(f"Unknown brain command: {brain_cmd}", file=sys.stderr)
def cmd_demo(args: argparse.Namespace) -> int:
    """Offline portfolio demo: seed fictional jobs, run the pipeline on mock LLM."""
    import os
    from src.core.config import get_settings

    os.environ.setdefault("PRIMARY_LLM_PROVIDER", "mock")
    os.environ.setdefault("PROFILE_DATA_DIR", "./data/sample")
    if getattr(args, "fresh_db", False):
        os.environ["DB_PATH"] = "./data/demo/careergraph_demo.db"
    get_settings.cache_clear()
    settings = get_settings()

    print("Operon-Job-Hunter demo - fictional candidate 'Alex Rivera', offline mock LLM")

    # 1. Seed fictional jobs + profile
    from src.demo.seeder import seed_demo
    mock_server = None
    ats_base = None
    if getattr(args, "with_submit", False):
        from tests.fixtures.mock_ats_server import MockATSServer
        mock_server = MockATSServer(port=0)
        mock_server.start()
        ats_base = mock_server.get_base_url()
        print(f"Mock ATS portal live at {ats_base}")

    jobs = seed_demo(db_path=settings.db_path, ats_base_url=ats_base)
    print(f"Seeded {len(jobs)} fictional jobs into {settings.db_path}")

    # 2. Run pipeline on the strongest N jobs (mock provider is deterministic)
    from src.pipeline.batch_dispatcher import BatchPipelineDispatcher
    n = getattr(args, "jobs", 5) or 5
    strong = [j for j in jobs if j.source == "demo"][:n]
    demo_checkpoints = "./data/demo/checkpoints.db"
    os.makedirs(os.path.dirname(demo_checkpoints), exist_ok=True)
    dispatcher = BatchPipelineDispatcher(
        max_workers=1,
        db_path=settings.db_path,
        checkpoints_db_path=demo_checkpoints,
    )
    from src.core.db.repository import EvaluationRepository
    from src.core.models import EvaluationResult
    eval_repo = EvaluationRepository(db_path=settings.db_path)
    results = []

    for job in strong:
        print(f"\n--- Pipeline: [{job.id}] {job.company}: {job.title}")
        outcome = dispatcher.process_single_job(job)
        results.append((job, outcome))
        eval_score = float(outcome.get("fit_score", 0.0) or 0.0)
        eval_repo.insert_evaluation(
            EvaluationResult(
                job_id=job.id,
                fit_score=eval_score,
                score=eval_score,
                reason="Mock evaluation: keyword-overlap heuristic.",
            )
        )
        print(f"    eval={outcome.get('fit_score')} tailored={bool(outcome.get('tailored'))}")

    # 3. Optional dry-run submission against mock ATS portal
    if getattr(args, "with_submit", False) and mock_server:
        portal_jobs = [j for j in jobs if j.portal_type in {"greenhouse", "lever"}]
        if portal_jobs:
            from src.core.models import CandidateProfile
            submitter = SubmitterEngine(dry_run=True)
            job = portal_jobs[0]
            print(f"\n--- Dry-run submission: [{job.id}] {job.company} -> {job.url}")
            art_repo = get_art_repo()
            artifacts = art_repo.get_by_job_id(job.id)
            receipt = submitter.submit(job, artifacts=artifacts, profile=CandidateProfile())
            print(f"    submission success={receipt.success} confirmation={receipt.confirmation_id}")

    # 4. Summary
    print("\nDemo complete. Run `python -m src.interface.cli.main ui` to explore Mission Control.")
    if mock_server:
        mock_server.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="careergraph",
        description="CareerGraph AI: Autonomous Agentic Job Search, Evaluation & Submitter CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # demo
    demo_p = subparsers.add_parser("demo", help="Offline portfolio demo (fictional data, mock LLM)")
    demo_p.add_argument("--jobs", type=int, default=5, help="how many jobs to run through the pipeline")
    demo_p.add_argument("--with-submit", action="store_true", help="also dry-run submit against an in-process mock ATS")
    demo_p.add_argument("--fresh-db", action="store_true", help="use a throwaway demo DB under data/demo/")

    # run
    run_p = subparsers.add_parser("run", help="Run end-to-end agentic StateGraph pipeline for job")
    run_p.add_argument("job_id", help="Job ID in database to run pipeline for")
    run_p.add_argument("--auto-submit", action="store_true", help="Auto submit on HITL approval")

    # status
    subparsers.add_parser("status", help="Show pipeline summary table")

    # scan
    scan_p = subparsers.add_parser("scan", help="Run discovery scanner across watchlist")
    scan_p.add_argument("--no-h1b", action="store_true", help="Do not filter for H-1B sponsorship")

    # ingest
    ingest_p = subparsers.add_parser("ingest", help="Ingest a specific job URL")
    ingest_p.add_argument("url", help="Job posting URL to ingest")

    # evaluate
    eval_p = subparsers.add_parser("evaluate", help="Run 7-Block evaluation on job")
    eval_p.add_argument("job_id", help="Job ID in database to evaluate")

    # tailor
    tailor_p = subparsers.add_parser("tailor", help="Generate ATS PDF resume and artifacts")
    tailor_p.add_argument("job_id", help="Job ID to tailor for")
    tailor_p.add_argument("--pages", type=int, default=None, choices=[1, 2], help="Target resume page budget (default: config setting)")

    # submit
    submit_p = subparsers.add_parser("submit", help="Submit job application via Playwright")
    submit_p.add_argument("job_id", help="Job ID to submit")
    submit_p.add_argument("--dry-run", action="store_true", default=False, help="Run dry run without final submit")

    # daemon
    daemon_p = subparsers.add_parser("daemon", help="Run background scanner & sync daemon")
    daemon_p.add_argument("--interval", type=int, default=300, help="Interval between cycles in seconds")
    daemon_p.add_argument("--iterations", type=int, default=None, help="Max iterations before exiting")
    daemon_p.add_argument("--heal-interval", type=int, default=0, help="Run self-healing every N iterations (0=disabled)")

    # heal — multi-stage healing orchestrator
    heal_p = subparsers.add_parser("heal", help="Run multi-stage self-healing orchestrator")
    heal_p.add_argument("--dry-run", action="store_true", help="Show what would be fixed without applying changes")
    heal_p.add_argument("--stage", type=str, default=None,
                        choices=["discovery", "gateway", "evaluation", "tailoring", "submission", "lifecycle"],
                        help="Heal specific stage only")
    heal_p.add_argument("--status", action="store_true", help="Show healer status and cooldowns")

    # errors
    errors_p = subparsers.add_parser("errors", help="Display structured error log")
    errors_p.add_argument("--unresolved", action="store_true", help="Show only unresolved errors")
    errors_p.add_argument("--company", type=str, default=None, help="Filter by company name")
    errors_p.add_argument("--source", type=str, default=None, help="Filter by source (crawler, gateway, submission, etc.)")
    errors_p.add_argument("--limit", type=int, default=50, help="Max errors to display")

    # ui
    ui_p = subparsers.add_parser("ui", help="Launch Mission Control Web UI")
    ui_p.add_argument("--host", default="0.0.0.0", help="Host interface to bind")
    ui_p.add_argument("--port", type=int, default=8000, help="Port to bind")
    ui_p.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")

    # brain — Career Brain subcommands
    brain_p = subparsers.add_parser("brain", help="Career Brain commands (query, status, models)")
    brain_sub = brain_p.add_subparsers(dest="brain_command", help="Brain subcommands")

    brain_query_p = brain_sub.add_parser("query", help="Query the Career Brain")
    brain_query_p.add_argument("query", help="Natural-language query")
    brain_query_p.add_argument("--mode", default="auto", choices=["auto", "avatar", "tailoring", "qa"],
                               help="Brain mode override")
    brain_query_p.add_argument("--job-desc", default=None, help="Job description for tailoring mode")

    brain_sub.add_parser("status", help="Check brain service status")
    brain_sub.add_parser("models", help="List fine-tuned brain models")

    # mission — P5c multi-agent platform
    mission_p = subparsers.add_parser("mission", help="P5c multi-agent platform")
    mission_sub = mission_p.add_subparsers(dest="mission_command", help="Mission subcommands")
    mission_sub.add_parser("start", help="Start all agents + SSE bridge (Ctrl+C to stop)")
    scan_m = mission_sub.add_parser("scan", help="One orchestrated discovery run")
    scan_m.add_argument("--companies", nargs="*", help="Watchlist company names (default: all)")
    scan_m.add_argument("--no-aggregators", dest="include_aggregators",
                        action="store_false", default=True)
    scan_m.add_argument("--filter-h1b", action="store_true", default=False)
    mission_sub.add_parser("status", help="Show recent agent decisions")
    resume_p = mission_sub.add_parser("resume", help="Resume job past submit interrupt")
    resume_p.add_argument("job_id")

    return parser


def _make_discovery_agent():
    from src.agents.discovery_orchestrator import DiscoveryOrchestratorAgent
    return DiscoveryOrchestratorAgent()


def cmd_mission(args: argparse.Namespace) -> int:
    """P5c multi-agent platform commands."""
    sub = getattr(args, "mission_command", None)
    if sub == "scan":
        names = getattr(args, "companies", None)
        summary = _make_discovery_agent().run_once(
            company_names=list(names) if names else None,
            include_aggregators=getattr(args, "include_aggregators", True),
            filter_h1b=getattr(args, "filter_h1b", False))
        print(f"jobs_ingested={summary['jobs_ingested']} "
              f"sources={len(summary['sources'])} in {summary['duration_sec']}s")
        return 0
    if sub == "status":
        from src.core.telemetry.agent_ledger import get_decisions
        recent = get_decisions(limit=10)
        print(f"recent agent decisions ({len(recent)}):")
        for d in recent:
            print(f"  [{d['timestamp']}] {d['agent_name']}/{d['decision_type']}: "
                  f"{d['reasoning'][:80]}")
        return 0
    if sub == "resume":
        from src.agents.application_agent import ApplicationAgent
        result = ApplicationAgent().resume_submission(args.job_id)
        print(f"resumed {args.job_id}: stage={result.get('current_stage')}")
        return 0
    if sub == "start":
        from src.agents.application_agent import ApplicationAgent
        from src.agents.discovery_orchestrator import DiscoveryOrchestratorAgent
        from src.agents.runtime import AgentRuntime
        runtime = AgentRuntime(
            [DiscoveryOrchestratorAgent(), ApplicationAgent()],
            bridge_sse=True)
        runtime.start()
        print("agents running: " + ", ".join(runtime.status()))
        try:
            import time as _time
            while True:
                _time.sleep(1)
        except KeyboardInterrupt:
            runtime.stop()
            print("agents stopped")
        return 0
    print(f"unknown mission command: {sub}", file=sys.stderr)
    return 2


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entrypoint."""
    if args is None:
        args = sys.argv[1:]

    parser = build_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command:
        parser.print_help()
        return 0

    command_handlers = {
        "demo": cmd_demo,
        "run": cmd_run,
        "status": cmd_status,
        "scan": cmd_scan,
        "ingest": cmd_ingest,
        "evaluate": cmd_evaluate,
        "tailor": cmd_tailor,
        "submit": cmd_submit,
        "daemon": cmd_daemon,
        "heal": cmd_heal,
        "errors": cmd_errors,
        "ui": cmd_ui,
        "brain": cmd_brain,
        "mission": cmd_mission,
    }

    handler = command_handlers.get(parsed_args.command)
    if handler:
        return handler(parsed_args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
