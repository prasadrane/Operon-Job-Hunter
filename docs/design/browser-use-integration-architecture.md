# Browser Use Integration Architecture

**Status**: IN PROGRESS — P1 complete, P2a complete, P2b complete (RoutingEngine + SessionValidator + tiered wiring), P2c complete (CredentialVault + config settings)  
**Author**: Software Architect Agent  
**Date**: 2026-08-25  
**Last Updated**: 2026-08-26  
**Scope**: CareerGraph Stage 4 (Submission) — Browser Use integration

---

## 1. Decision: Integrate or Replace

### Verdict: **Integrate as Tier-2 fallback; do NOT replace Stage 4**

```
DECISION MATRIX
┌──────────────────┬──────────┬───────────┬──────────────────────────────┐
│ Criterion        │ Weight   │ BU Score  │ Rationale                    │
├──────────────────┼──────────┼───────────┼──────────────────────────────┤
│ Form accuracy    │ 30%      │ 7/10      │ Good on novel DOMs, worse on │
│                  │          │           │ known ATS vs deterministic   │
│ Anti-detection   │ 20%      │ 8/10      │ Forked Chromium, but         │
│                  │          │           │ LinkedIn specifically        │
│                  │          │           │ targets BU signatures        │
│ Token cost       │ 15%      │ 5/10      │ ~68s avg task, ~2-5k tokens  │
│                  │          │           │ per form vs Stagehand <100   │
│ Python fit       │ 15%      │ 9/10      │ Native async Python, matches │
│                  │          │           │ our stack                    │
│ Control/audit    │ 10%      │ 6/10      │ LLM decides actions = less   │
│                  │          │           │ deterministic than selectors │
│ Maturity         │ 10%      │ 8/10      │ 111k stars, active CDP       │
│                  │          │           │ migration complete           │
└──────────────────┴──────────┴───────────┴──────────────────────────────┘
WEIGHTED: 7.05 / 10 — useful but not a wholesale replacement.
```

### Routing Decision (3-tier)

| Tier | Engine | When Used | Why |
|------|--------|-----------|-----|
| **T1: FastPath** | `FastPathSubmitter` (existing) | Known ATS (Greenhouse/Lever/Ashby/Workday) with cached selectors in `PORTAL_SELECTORS` or `data/ats_quirks.json` | Zero LLM cost, deterministic, ~2-5s, auditable |
| **T2: Browser Use** | `Agent` with CDP | Unknown/generic portals, dynamic SPAs, ATS not in T1 catalog, T1 selector failures after healing | Handles novel DOMs, self-healing, ~30-90s |
| **T3: WebSurfer** | `WebSurferAgent` (existing, rebuilt) | Fallback when BU fails, or headless-restricted environments | Rule-based, no LLM cost, deterministic-ish |

### FastPath Decision: **KEEP and wire in**

FastPath is dead code today (never imported by `submitter_engine.py`). Fix:
- Wire `FastPathSubmitter` into `SubmitterEngine.submit()` as the first attempt for known ATS
- Use `FormHealingEngine` inline when FastPath selectors fail (3 retries)
- Only escalate to Browser Use after FastPath + healing both fail

### WebSurfer Decision: **DECOMMISSION as primary; keep as rule-based fallback**

WebSurferAgent's AXTree/SoM pipeline is elegant but:
- BU does the same thing better (CDP-native DOM extraction + vision fallback)
- WebSurfer's rule-based decision engine is fragile for novel portals
- Keep the `ActionDispatcher` + `handlers.py` as a deterministic fallback layer that BU can call via custom actions

---

## 2. Architecture Diagram

### 2.1 Component Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     PipelineGraphState (LangGraph)                       │
│  job_id | company | url | profile | artifacts | portal_type | ...       │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │ node_submit_and_verify()
                              │ @with_circuit_breaker(120s) ← raised from 45s
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       SubmitterEngine.submit()                           │
│                                                                          │
│  ┌──────────────┐   ┌──────────────────┐   ┌─────────────────────────┐ │
│  │ Preflight    │──▶│ SessionValidator │──▶│ CaptchaGate             │ │
│  │ Screener     │   │ (NEW)            │   │ (detect + solve + HITL) │ │
│  └──────────────┘   └──────────────────┘   └─────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    RoutingEngine (NEW)                              │ │
│  │                                                                     │ │
│  │  if portal_type in KNOWN_ATS and selectors cached:                  │ │
│  │      ┌─────────────────────┐                                        │ │
│  │      │ T1: FastPathSubmit  │  deterministic, 0 LLM tokens           │ │
│  │      │ + FormHealingEngine │  3 retries with fuzzy recovery         │ │
│  │      └─────────┬───────────┘                                        │ │
│  │                │ on_failure                                         │ │
│  │                ▼                                                    │ │
│  │  else:         ┌─────────────────────────────────┐                  │ │
│  │      ┌────────▶│ T2: BrowserUseAgent             │                  │ │
│  │      │         │ (Browser Use Agent w/ CDP)       │  LLM-driven     │ │
│  │      │         │ + CareerGraph custom actions      │  2-8k tokens    │ │
│  │      │         └───────────┬──────────────────────┘                  │ │
│  │      │                     │ on_failure                              │ │
│  │      │                     ▼                                         │ │
│  │      │         ┌─────────────────────────────┐                       │ │
│  │      │         │ T3: WebSurferAgent (legacy)  │  rule-based           │ │
│  │      │         │ + AXTree + SoM               │  no LLM              │ │
│  │      └─────────└─────────────────────────────┘                       │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ ReceiptCollector: screenshot + confirmation extraction + audit    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Browser Use Agent Internal Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ BrowserUseAgent (wraps browser_use.Agent)                        │
│                                                                   │
│  task: "Apply to {company} {title} at {url}"                     │
│  llm: ChatOpenAI(base_url=alibaba_base_url, api_key=...)         │
│        └─ OR ChatBrowserUse() if BROWSER_USE_API_KEY set         │
│  page_extraction_llm: same model, isolated context               │
│  controller: CareerGraphController (custom)                      │
│  use_vision: "auto"  (DOM-first, screenshots on LLM request)    │
│  max_failures: 3                                                  │
│  fallback_llm: ChatGoogle(model="gemini-2.5-flash")              │
│  output_model_schema: SubmissionResult (Pydantic)                │
│  before_step: _audit_hook                                        │
│  after_step: _checkpoint_hook                                    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ CareerGraphController (extends browser_use.Controller)  │    │
│  │                                                          │    │
│  │  @action("Upload resume PDF")                            │    │
│  │  upload_resume(file_path, browser_context)               │    │
│  │                                                          │    │
│  │  @action("Fill candidate profile fields")                │    │
│  │  fill_profile(profile_dict, browser_context)             │    │
│  │                                                          │    │
│  │  @action("Answer screening question")                    │    │
│  │  answer_question(question_text, job_context)             │    │
│  │                                                          │    │
│  │  @action("Submit application")                           │    │
│  │  submit_and_confirm(browser_context)                     │    │
│  │                                                          │    │
│  │  @action("Detect CAPTCHA")                               │    │
│  │  detect_and_solve_captcha(browser_context)               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Anti-Detection Layer                                     │    │
│  │  • Patchright (drop-in Playwright replacement)           │    │
│  │  • browser_use fork's Chromium (if using BU cloud)       │    │
│  │  • Static residential proxy (per-account)                │    │
│  │  • Behavioral sim: Poisson typing + Bézier mouse         │    │
│  │  • Headed mode (not headless) for flagged portals        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Auth/Session Layer                                       │    │
│  │  • SessionValidator: pre-flight cookie + endpoint probe  │    │
│  │  • CredentialVault: keyring-backed per-site creds        │    │
│  │  • TOTPInjector: pyotp for 2FA codes                     │    │
│  │  • TelegramRelay: SMS→HITL escalation                    │    │
│  │  • Persistent context: data/browser_profile/ (existing)  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Data Flow (detailed)

```
PipelineGraphState
  │
  ├─ job: JobPosting {id, company, title, url, portal_type}
  ├─ profile: CandidateProfile {first_name, last_name, email, phone, ...}
  ├─ artifacts: TailoredArtifacts {resume_pdf_path, cover_letter_path}
  ├─ credentials: dict  ← NEW (from CredentialVault, not persisted to checkpoints)
  │
  ▼
SubmitterEngine.submit(job, profile, artifacts)
  │
  ├─ 1. PreflightScreener.screen_page(page, profile)
  │     └─ knockout/blacklist → early return with screenshot
  │
  ├─ 2. SessionValidator.validate(url, portal_type)
  │     ├─ Check persistent context cookies valid
  │     ├─ Probe protected endpoint (e.g. /api/me)
  │     ├─ If expired → CredentialVault.fetch(portal_type) → login flow
  │     └─ If 2FA needed → TOTPInjector / TelegramRelay → HITL
  │
  ├─ 3. CaptchaGate.check(page)
  │     ├─ No captcha → continue
  │     ├─ Cloudflare Turnstile → Patchright auto-passes
  │     ├─ reCAPTCHA → CapSolver API call (NEW integration)
  │     └─ Unknown → HITL via Telegram (existing path, timeout raised to 120s)
  │
  ├─ 4. RoutingEngine.select(portal_type, url, page)
  │     │
  │     ├─ T1: FastPathSubmitter.fill_profile(page, profile, resume_path)
  │     │     ├─ DOM quiescence wait
  │     │     ├─ Ordered selector tuples (PORTAL_SELECTORS)
  │     │     ├─ Learned quirks (data/ats_quirks.json)
  │     │     ├─ On selector fail → FormHealingEngine (3 attempts)
  │     │     └─ FastPathSubmitter.submit(page) → confirmation check
  │     │
  │     ├─ T2: BrowserUseAgent.run(task, profile, artifacts)
  │     │     ├─ Instantiate Agent with CareerGraphController
  │     │     ├─ Build task prompt from profile + job context
  │     │     ├─ agent.run() → LLM drives browser via CDP
  │     │     ├─ Custom actions: upload_resume, fill_profile, answer_question
  │     │     ├─ Hooks: before_step → audit log; after_step → checkpoint
  │     │     └─ Returns SubmissionResult (Pydantic validated)
  │     │
  │     └─ T3: WebSurferAgent (legacy fallback)
  │           ├─ AXTree parse → SoM annotate → rule-based decide
  │           └─ ActionDispatcher → handlers
  │
  └─ 5. ReceiptCollector.capture(page, job, profile)
        ├─ Screenshot (full page)
        ├─ Confirmation ID extraction (regex + DOM)
        ├─ Audit log entry
        └─ Return SubmissionReceipt
```

### 2.4 Circuit Breaker Integration

```
CURRENT:  @with_circuit_breaker(45s)     ← TOO SHORT
PROPOSED: @with_circuit_breaker(180s)    ← 3 min for full submit flow

BREAKDOWN:
  Preflight:           5s
  Session validation: 10s
  CAPTCHA solve:      30s (CapSolver) / 120s (HITL)
  T1 FastPath:        15s (deterministic)
  T2 Browser Use:     90s (LLM-driven, avg 68s + margin)
  T3 WebSurfer:       30s (rule-based)
  Receipt capture:     5s
  ─────────────────────────
  TOTAL worst case:  175s ≈ 180s

INNER TIMEOUTS:
  Each tier gets its own asyncio timeout:
    T1: 15s → escalate to T2
    T2: 90s → escalate to T3
    T3: 30s → hard fail
```

### 2.5 Fallback Chain

```
              ┌──────────┐
              │  Start    │
              └────┬─────┘
                   │
          ┌────────▼────────┐
          │  T1: FastPath   │
          │  (deterministic)│
          └────────┬────────┘
                   │ failure OR unknown ATS
          ┌────────▼────────┐
          │  T2: BrowserUse │
          │  (LLM-driven)   │
          └────────┬────────┘
                   │ failure OR max_failures hit
          ┌────────▼────────┐
          │  T3: WebSurfer  │
          │  (rule-based)   │
          └────────┬────────┘
                   │ failure
          ┌────────▼────────┐
          │  HITL Escalate  │
          │  (Telegram)     │
          └────────┬────────┘
                   │ timeout
          ┌────────▼────────┐
          │  HARD FAIL      │
          │  screenshot +   │
          │  error log      │
          └─────────────────┘
```

---

## 3. API Contract Design

### 3.1 New Module: `src/pipeline/4_submission/browser_use_agent.py`

```python
"""Browser Use integration for CareerGraph Stage 4 submission."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from browser_use import Agent
from browser_use.controller import Controller

logger = logging.getLogger(__name__)


# ── Input Schema ──────────────────────────────────────────────────────────────

class SubmissionTask(BaseModel):
    """Input contract for a Browser Use submission task."""
    job_url: str = Field(..., description="Full URL to the job application page")
    company: str = Field(..., description="Company name")
    title: str = Field(..., description="Job title")
    portal_type: str = Field(default="unknown", description="ATS platform identifier")
    
    # Candidate data
    profile: Dict[str, Any] = Field(..., description="Candidate profile fields")
    resume_pdf_path: Optional[str] = Field(None, description="Absolute path to tailored resume PDF")
    cover_letter_path: Optional[str] = Field(None, description="Absolute path to cover letter PDF")
    
    # Credentials (from CredentialVault, NOT persisted)
    credentials: Optional[Dict[str, str]] = Field(None, description="Login credentials if needed")
    
    # Job context for question answering
    job_description: Optional[str] = Field(None, description="Full JD for question answering")
    star_narratives: Optional[list] = Field(None, description="STAR narratives from GraphRAG")
    
    # Behavior controls
    use_vision: str = Field(default="auto", description="auto|true|false")
    max_steps: int = Field(default=30, description="Maximum agent steps before giving up")
    timeout_seconds: int = Field(default=90, description="Per-task timeout")


# ── Output Schema ─────────────────────────────────────────────────────────────

class SubmissionResult(BaseModel):
    """Structured output from Browser Use submission."""
    success: bool = Field(..., description="Whether submission completed")
    confirmation_id: Optional[str] = Field(None, description="Receipt/confirmation code")
    screenshot_path: Optional[str] = Field(None, description="Path to final screenshot")
    steps_taken: int = Field(default=0, description="Number of agent steps executed")
    tokens_used: int = Field(default=0, description="Approximate token consumption")
    duration_seconds: float = Field(default=0.0, description="Wall-clock duration")
    error_message: Optional[str] = Field(None, description="Error description on failure")
    filled_fields: Dict[str, Any] = Field(default_factory=dict, description="Fields that were filled")
    questions_answered: int = Field(default=0, description="Custom questions answered")
    tier_used: str = Field(default="T2", description="Which engine handled it: T1/T2/T3")
    audit_trail: list = Field(default_factory=list, description="Step-by-step audit log")


# ── Custom Controller ─────────────────────────────────────────────────────────

class CareerGraphController(Controller):
    """Custom Browser Use controller with CareerGraph domain actions."""
    
    def __init__(self, profile: dict, job_context: dict, qa_synthesizer=None):
        super().__init__()
        self.profile = profile
        self.job_context = job_context
        self.qa_synthesizer = qa_synthesizer
        self._register_actions()
    
    def _register_actions(self):
        """Register all custom actions with the controller."""
        
        @self.action("Upload resume PDF to file input")
        async def upload_resume(file_path: str, browser_context=None):
            """Upload the candidate's resume PDF to the current file input."""
            if not file_path or not os.path.exists(file_path):
                return f"Resume file not found: {file_path}"
            # Use CDP to set file on input[type=file]
            # Implementation in §3.3
            return f"Uploaded resume: {os.path.basename(file_path)}"
        
        @self.action("Answer application screening question")
        async def answer_question(question: str) -> str:
            """Generate an answer for a custom application question using 
            the candidate's profile, resume, and STAR narratives."""
            if self.qa_synthesizer:
                return self.qa_synthesizer.synthesize_answer(
                    question=question,
                    profile=self.profile,
                    job_context=self.job_context,
                )
            return "Unable to answer — no synthesizer available"
        
        @self.action("Fill candidate profile fields")
        async def fill_profile_fields(field_name: str, value: str) -> str:
            """Fill a specific profile field. Use this when you identify a form 
            field that matches candidate data (name, email, phone, etc)."""
            # This is a hint action — the LLM uses it to map fields
            # Actual filling happens via standard type/fill actions
            return f"Field '{field_name}' mapped to value (use type action to fill)"
    
    # ... implementation continues in §3.3


# ── Main Agent Wrapper ────────────────────────────────────────────────────────

class BrowserUseSubmissionAgent:
    """Wraps browser_use.Agent for CareerGraph submission tasks."""
    
    def __init__(
        self,
        llm=None,                    # LangChain-compatible LLM instance
        fallback_llm=None,           # Backup LLM on failure
        use_vision: str = "auto",
        max_failures: int = 3,
        max_steps: int = 30,
        qa_synthesizer=None,
        behavior_config: Optional[dict] = None,
    ):
        self.llm = llm or self._default_llm()
        self.fallback_llm = fallback_llm or self._default_fallback()
        self.use_vision = use_vision
        self.max_failures = max_failures
        self.max_steps = max_steps
        self.qa_synthesizer = qa_synthesizer
        self.behavior_config = behavior_config or {}
    
    async def submit(self, task: SubmissionTask) -> SubmissionResult:
        """Execute a submission task via Browser Use Agent.
        
        Returns structured SubmissionResult with audit trail.
        """
        # Build controller with task-specific context
        controller = CareerGraphController(
            profile=task.profile,
            job_context={
                "company": task.company,
                "title": task.title,
                "url": task.job_url,
                "description": task.job_description,
                "star_narratives": task.star_narratives,
            },
            qa_synthesizer=self.qa_synthesizer,
        )
        
        # Compose task prompt
        task_prompt = self._build_task_prompt(task)
        
        # Create agent
        agent = Agent(
            task=task_prompt,
            llm=self.llm,
            controller=controller,
            use_vision=task.use_vision if task.use_vision != "auto" else "auto",
            max_failures=self.max_failures,
            fallback_llm=self.fallback_llm,
            output_model_schema=SubmissionResult,
            before_step=self._before_step_hook,
            after_step=self._after_step_hook,
        )
        
        # Execute with timeout
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                agent.run(),
                timeout=task.timeout_seconds,
            )
            duration = time.monotonic() - start
            
            # Extract structured result
            return self._extract_result(result, duration)
            
        except asyncio.TimeoutError:
            return SubmissionResult(
                success=False,
                error_message=f"Browser Use timed out after {task.timeout_seconds}s",
                duration_seconds=task.timeout_seconds,
                tier_used="T2",
            )
        except Exception as e:
            logger.exception("Browser Use submission failed: %s", e)
            return SubmissionResult(
                success=False,
                error_message=str(e),
                duration_seconds=time.monotonic() - start,
                tier_used="T2",
            )
    
    def _build_task_prompt(self, task: SubmissionTask) -> str:
        """Compose natural language task description for the agent."""
        return f"""Go to {task.job_url} and complete the job application for 
{task.title} at {task.company}.

Steps:
1. Navigate to the application form
2. If login is required, use the provided credentials
3. Fill in all personal information fields using the candidate profile
4. Upload the resume PDF from: {task.resume_pdf_path}
5. Answer any screening questions using the job context
6. Review the application
7. Click submit
8. Wait for confirmation and extract the confirmation/receipt number

Important:
- Do NOT submit if any required field is empty
- If a CAPTCHA appears, wait for it to be solved
- Take a screenshot of the confirmation page
- Report the confirmation number if visible"""
    
    # Hooks, result extraction, LLM factory methods...
    # See §3.3
```

### 3.2 Input/Output Contract Summary

**INPUT: `SubmissionTask` (Pydantic model)**
```
job_url: str                    — required
company: str                    — required
title: str                      — required
portal_type: str                — default "unknown"
profile: dict                   — required (CandidateProfile.model_dump())
resume_pdf_path: str?           — optional
cover_letter_path: str?         — optional
credentials: dict?              — optional (from CredentialVault)
job_description: str?           — optional (for question answering)
star_narratives: list?          — optional (from GraphRAG archival memory)
use_vision: str                 — "auto" | "true" | "false"
max_steps: int                  — default 30
timeout_seconds: int            — default 90
```

**OUTPUT: `SubmissionResult` (Pydantic model)**
```
success: bool                   — required
confirmation_id: str?           — extracted receipt code
screenshot_path: str?           — final page screenshot
steps_taken: int                — agent step count
tokens_used: int                — LLM token consumption
duration_seconds: float         — wall-clock time
error_message: str?             — on failure
filled_fields: dict             — audit: what was filled
questions_answered: int         — custom Q count
tier_used: str                  — "T1" | "T2" | "T3"
audit_trail: list[dict]         — step-by-step log
```

### 3.3 Custom Actions (detail)

```python
# Resume upload via CDP
@self.action("Upload resume PDF")
async def upload_resume(browser_context):
    file_input = await browser_context.query_selector('input[type="file"]')
    if file_input:
        await file_input.set_input_files(task.resume_pdf_path)
        return "Resume uploaded"
    return "No file input found"

# CAPTCHA detection + solve
@self.action("Check and solve CAPTCHA")
async def check_captcha(browser_context):
    page = await browser_context.get_current_page()
    captcha_detected = await page.evaluate("""
        () => {
            return !!(
                document.querySelector('.cf-turnstile') ||
                document.querySelector('.g-recaptcha') ||
                document.querySelector('[data-sitekey]') ||
                document.querySelector('.h-captcha')
            );
        }
    """)
    if captcha_detected:
        # Call CapSolver API
        from .captcha_solver import CapSolverClient
        solver = CapSolverClient()
        solved = await solver.solve(page)
        return "CAPTCHA solved" if solved else "CAPTCHA solve failed"
    return "No CAPTCHA detected"

# Confirmation extraction
@self.action("Extract confirmation number")
async def extract_confirmation(browser_context) -> str:
    page = await browser_context.get_current_page()
    content = await page.content()
    import re
    patterns = [
        r'(?:confirmation|application|reference)\s*(?:#|id|code)?[:\s]*([A-Za-z0-9\-_]{4,25})',
        r'GH-CONF-[A-Za-z0-9\-]+',
        r'LEVER-CONF-[A-Za-z0-9\-]+',
    ]
    for p in patterns:
        m = re.search(p, content, re.I)
        if m:
            return m.group(0)
    # Fallback: look for "thank you" text
    if "thank you" in content.lower():
        return "CONFIRMED-RECEIPT"
    return "NO_CONFIRMATION_FOUND"
```

### 3.4 Error Types

```python
class SubmissionError(Exception):
    """Base error for submission pipeline."""
    pass

class PreflightError(SubmissionError):
    """Preflight screening blocked submission (blacklist/knockout)."""
    pass

class AuthError(SubmissionError):
    """Authentication/session validation failed."""
    retryable = True

class CaptchaError(SubmissionError):
    """CAPTCHA could not be solved within timeout."""
    retryable = False

class FormFillError(SubmissionError):
    """Form filling failed after all healing attempts."""
    retryable = True

class ConfirmationError(SubmissionError):
    """Submission clicked but no confirmation detected."""
    retryable = False

class TierExhaustedError(SubmissionError):
    """All three tiers (T1/T2/T3) failed."""
    retryable = False
```

---

## 3.5 Submission Audit Layer

**Status**: Implemented in P2a — `src/pipeline/4_submission/submission_audit.py`

Every major browser action is logged to SQLite (`submission_audit_log` table) for:
1. **Debugging** submission failures — trace exactly which action failed, on which selector, with what error
2. **Lifecycle learning** — analyze patterns across submissions to improve form-fill accuracy
3. **Observability** — SSE broadcast via AGENT_LOGS for real-time UI visibility

### AuditEntry Schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | TEXT PK | UUID |
| `submission_id` | TEXT | Groups all actions for one submission |
| `action_type` | TEXT | `navigate`, `fill_field`, `upload_file`, `click`, `captcha_detect`, `submit`, `confirm_extract`, `answer_question` |
| `target` | TEXT | CSS selector, URL, or field name |
| `success` | INTEGER | 0/1 |
| `job_id` | TEXT | Job posting ID |
| `company` | TEXT | Company name |
| `portal_type` | TEXT | ATS platform |
| `tier` | TEXT | T1/T2/T3 |
| `step_index` | INTEGER | Sequential step within submission |
| `duration_ms` | REAL | Action duration |
| `error_detail` | TEXT | Error message if failed |
| `metadata` | TEXT (JSON) | Extra context (field value length, screenshot path, etc.) |
| `timestamp` | TEXT | ISO format |

### Integration Points

- **BrowserUseSubmissionAgent**: `before_step`/`after_step` hooks feed into auditor
- **CareerGraphController**: Custom actions (upload_resume, answer_question, fill_profile) log via `auditor_callback`
- **Dual-write**: SQLite persistence + AGENT_LOGS SSE broadcast
- **Kill switch**: `SUBMISSION_AUDIT_ENABLED=false` disables persistence (logs still go to AGENT_LOGS)

---

## 4. Migration Path

### Phase 1: Wire FastPath + Fix Bugs (Week 1-2) — **QUICK WIN**

**Goal**: Make existing code work. Zero new dependencies.

| Task | File | Change |
|------|------|--------|
| 1a. Fix `submit()` signature bug | `state_machine.py:329` | Pass `profile=state["profile"]`, `artifacts=state["artifacts"]` |
| 1b. Wire FastPath into SubmitterEngine | `submitter_engine.py` | Import `FastPathSubmitter`, try T1 first before adapter |
| 1c. Wire FormHealingEngine | `fastpath_engine.py` | Already done internally — verify integration |
| 1d. Raise circuit breaker | `state_machine.py:389` | `with_circuit_breaker(120)` (from 45s) |
| 1e. Add routing to adapter chain | `adapters/__init__.py` | Add `WorkdayAgenticSubmitter` to `ATS_ADAPTERS` |
| 1f. Unit tests | `tests/unit/test_submission/` | Tests for FastPath + healing + routing |

**Deliverable**: T1 FastPath works for Greenhouse/Lever/Ashby. Deterministic, fast, zero LLM cost.

### Phase 2: Browser Use Integration (Week 3-5) — **CORE WORK**

| Task | File | Change | Status |
|------|------|--------|--------|
| 2a. Add dependency | `requirements.txt` | `browser-use>=0.13.8`, `langchain-openai>=0.3.0` | ✅ Done (P2a) |
| 2b. Create BrowserUseSubmissionAgent | `src/pipeline/4_submission/browser_use_agent.py` | New module (see §3) | ✅ Done (P2a) |
| 2c. Create CareerGraphController | Same file | Custom actions for resume upload, Q&A, confirmation | ✅ Done (P2a) |
| 2c+. Create Submission Audit Layer | `src/pipeline/4_submission/submission_audit.py` | AuditEntry + SubmissionAuditor + log_audit() | ✅ Done (P2a) |
| 2d. Create RoutingEngine | `src/pipeline/4_submission/routing_engine.py` | T1/T2/T3 decision logic | ✅ Done (P2b) |
| 2e. Create SessionValidator | `src/pipeline/4_submission/session_validator.py` | Cookie check + login probe | ✅ Done (P2b) |
| 2f. Create CredentialVault | `src/core/credentials/vault.py` | keyring-backed credential store | ✅ Done (P2c) |
| 2g. Integrate CapSolver | `src/pipeline/4_submission/captcha_solver.py` | External CAPTCHA API client | P2d |
| 2h. Patchright swap | `browser_manager.py` | Replace `playwright` import with `patchright` | P2e |
| 2i. Config additions | `src/core/config.py` | New settings (see §6) | ✅ Done (P2a + P2c credential settings) |
| 2j. Wire into SubmitterEngine | `submitter_engine.py` | Add T2 fallback after T1 failure | P2b |
| 2k. Integration tests | `tests/integration/test_browser_use.py` | Mock ATS + Browser Use agent tests | P2b |

**Deliverable**: T2 Browser Use handles unknown/generic portals. T1→T2 fallback chain works.

### Phase 3: Full Integration + Hardening (Week 6-8)

| Task | File | Change |
|------|------|--------|
| 3a. Anti-detection layer | `src/pipeline/4_submission/stealth/` | Behavioral sim (Bézier mouse, Poisson typing) |
| 3b. TOTP 2FA support | `src/core/credentials/totp.py` | pyotp-based auto-2FA |
| 3c. Mid-submission checkpointing | `submitter_engine.py` | Serialize agent state at each step |
| 3d. Retry strategy | `submitter_engine.py` | Configurable retry per error type |
| 3e. Observability | `src/core/telemetry/` | Per-step audit trail, token tracking, cost |
| 3f. Decommission WebSurfer | `websurfer_agent.py` | Mark as T3 fallback only, reduce maintenance |
| 3g. Performance tuning | Multiple | Token optimization, caching, KV reuse |
| 3h. Production runbook | `docs/runbooks/submission.md` | Operational procedures |

**Deliverable**: Production-ready 3-tier submission with full observability.

### What Stays Unchanged

| Component | Status | Reason |
|-----------|--------|--------|
| `PreflightScreener` | ✅ Keep | Works well, no BU dependency |
| `BaseATSAdapter` + per-ATS adapters | ✅ Keep | T1 tier uses these |
| `PORTAL_SELECTORS` (FastPath) | ✅ Keep | Core of T1 deterministic path |
| `FormHealingEngine` | ✅ Keep | Used by T1 and reusable in T2 |
| `dom_quiescence` | ✅ Keep | Used by FastPath |
| `BrowserManager` (stealth) | 🔄 Migrate | Swap to Patchright in Phase 2 |
| `QASynthesizer` | 🔄 Extend | Used by Browser Use custom actions |
| `WizardStateManager` | 🔄 Repurpose | Mid-submission checkpointing for BU |

---

## 5. Risk Register

| # | Risk | Impact | Probability | Mitigation |
|---|------|--------|-------------|------------|
| R1 | **LLM hallucination clicks wrong button** (e.g. "Delete" instead of "Submit") | 🔴 CRITICAL — submits wrong data or destroys application | Medium | `output_model_schema` validation; dry-run mode for first 30 days; confirm-before-submit custom action that screenshots pre-submit state; human approval gate for first N applications |
| R2 | **Token cost explosion** — BU uses 5-15k tokens per form fill | 🟠 HIGH — $0.01-0.05/application adds up at scale | High | T1 FastPath handles 60-70% of applications at zero LLM cost; T2 only for unknown portals; cache task prompts for KV reuse; set `max_steps=30` cap; monitor `calculate_cost=True` |
| R3 | **Browser Use CDP breaks on Playwright-specific code** — we use Playwright stealth/profiles | 🟠 HIGH — stealth layer fails | Medium | Patchright is a Playwright drop-in replacement with CDP fixes; test all stealth injections against Patchright first; keep Playwright as fallback if Patchright fails |
| R4 | **LinkedIn/account bans from detection** — BU's Chromium fork has known signatures | 🔴 CRITICAL — loses access to platform | Medium | LinkedIn is NOT in our target list (we target corporate career sites, not LinkedIn); use Patchright + behavioral sim; rate limit 5-10 apps/day; 4-week account warming; static residential IP per account |
| R5 | **Circuit breaker trips during BU agent run** — 90s agent vs 45s breaker | 🟠 HIGH — kills in-flight submission | Certain (if not fixed) | Raise circuit breaker to 180s (Phase 1 task 1d); inner per-tier timeouts prevent runaway; BU `max_failures=3` prevents infinite loops |
| R6 | **Prompt injection via webpage text** — malicious job page injects instructions | 🟠 HIGH — agent executes attacker's commands | Low-Medium | BU's DOM extraction sanitizes text; add `override_system_message` with strict role constraints; never trust page text as instructions; scope agent actions to form-fill only |
| R7 | **Credential leakage through checkpoints** — passwords in PipelineGraphState | 🔴 CRITICAL — SQLite checkpoint DB has plaintext passwords | High (current bug) | CredentialVault uses OS keyring, NOT pipeline state; credentials passed via ephemeral reference, never serialized; add `prune_transient_state` to strip credential refs before checkpoint |
| R8 | **Browser Use API dependency** — if `BROWSER_USE_API_KEY` service goes down | 🟡 MEDIUM — T2 tier unavailable | Low | OSS mode works without API key (uses local Chromium); fallback_llm chain (Alibaba → Gemini → OpenRouter); T1 FastPath still works independently |

### Rollback Strategy

Each phase is independently rollbackable:

- **Phase 1 rollback**: Remove FastPath import from `submitter_engine.py` → reverts to adapter-only (current behavior)
- **Phase 2 rollback**: Remove `browser_use` from requirements, disable T2 in RoutingEngine → falls back to T1 + T3
- **Phase 3 rollback**: Disable behavioral sim, TOTP, checkpointing → reverts to Phase 2 baseline

**Kill switch**: Set `SUBMISSION_BROWSER_USE_ENABLED=false` in env → RoutingEngine skips T2 entirely.

---

## 6. Configuration Changes

### 6.1 New Settings in `src/core/config.py`

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # ── Browser Use Integration ──────────────────────────────────────────
    browser_use_enabled: bool = True
    browser_use_api_key: Optional[str] = None          # For ChatBrowserUse (optional)
    browser_use_vision: str = "auto"                    # "auto" | "true" | "false"
    browser_use_max_steps: int = 30
    browser_use_max_failures: int = 3
    browser_use_timeout_seconds: int = 90
    browser_use_llm_provider: str = "alibaba"           # Which LLM provider for BU
    browser_use_model: str = "qwen-vl-max"              # Vision-capable model
    browser_use_fallback_provider: str = "gemini"
    browser_use_fallback_model: str = "gemini-2.5-flash"
    
    # ── Submission Tier Routing ──────────────────────────────────────────
    submission_t1_enabled: bool = True                  # FastPath deterministic
    submission_t2_enabled: bool = True                  # Browser Use LLM-driven
    submission_t3_enabled: bool = True                  # WebSurfer rule-based
    submission_circuit_breaker_seconds: float = 180.0   # Raised from 45s
    submission_max_retries: int = 2                     # Per-tier retry count
    
    # ── CAPTCHA Solving ──────────────────────────────────────────────────
    captcha_solver_provider: str = "capsolver"          # "capsolver" | "2captcha" | "hitl"
    captcha_solver_api_key: Optional[str] = None
    captcha_solver_timeout_seconds: int = 30
    
    # ── Anti-Detection ───────────────────────────────────────────────────
    stealth_backend: str = "patchright"                 # "patchright" | "playwright_stealth"
    behavioral_simulation: bool = True
    typing_speed_wpm: int = 85                          # Human-like typing speed
    mouse_bezier_curves: bool = True
    
    # ── Credential Vault ─────────────────────────────────────────────────
    credential_backend: str = "keyring"                 # "keyring" | "env" | "file"
    totp_enabled: bool = False
    totp_secrets_backend: str = "keyring"
```

### 6.2 New Dependencies in `requirements.txt`

```
# Browser Use integration
browser-use>=0.13.8
patchright>=1.50.0          # Drop-in Playwright replacement with anti-detection

# Credential management
keyring>=25.0.0              # OS-native credential storage
pyotp>=2.9.0                 # TOTP 2FA generation

# CAPTCHA solving
capsolver-python>=1.5.0      # CapSolver API client (or 2captcha-python)

# Behavioral simulation
pyautogui>=0.9.54            # Mouse trajectory (fallback if CDP mouse fails)
```

### 6.3 New Environment Variables

```env
# Browser Use
BROWSER_USE_API_KEY=                    # Optional, for hosted LLM
BROWSER_USE_VISION=auto
BROWSER_USE_MAX_STEPS=30
BROWSER_USE_TIMEOUT=90

# CAPTCHA Solving
CAPTCHA_SOLVER_PROVIDER=capsolver
CAPTCHA_SOLVER_API_KEY=                 # From capsolver.com

# Credential Vault
CREDENTIAL_BACKEND=keyring

# Anti-Detection
STEALTH_BACKEND=patchright
BEHAVIORAL_SIMULATION=true
```

---

## 7. Testing Strategy

### 7.1 Unit Tests

| Test File | Coverage |
|-----------|----------|
| `tests/unit/test_browser_use_agent.py` | `BrowserUseSubmissionAgent.submit()` with mocked Agent |
| `tests/unit/test_career_graph_controller.py` | Custom action registration + execution |
| `tests/unit/test_routing_engine.py` | T1/T2/T3 routing decisions |
| `tests/unit/test_session_validator.py` | Cookie validation + login probe |
| `tests/unit/test_credential_vault.py` | keyring CRUD + TOTP generation |
| `tests/unit/test_captcha_solver.py` | CapSolver API mock + fallback to HITL |

**Pattern**: Mock `browser_use.Agent` entirely. Test the wrapper logic, not the LLM.

```python
# Example: test_routing_engine.py
def test_routing_known_ats():
    engine = RoutingEngine()
    tier = engine.select(portal_type="greenhouse", url="https://boards.greenhouse.io/...")
    assert tier == "T1"

def test_routing_unknown_portal():
    engine = RoutingEngine()
    tier = engine.select(portal_type="unknown", url="https://careers.weirdstartup.com/...")
    assert tier == "T2"

def test_routing_t1_disabled():
    engine = RoutingEngine(t1_enabled=False)
    tier = engine.select(portal_type="greenhouse", url="...")
    assert tier == "T2"  # Skips T1 when disabled
```

### 7.2 Integration Tests

| Test File | Coverage |
|-----------|----------|
| `tests/integration/test_submission_e2e.py` | Full T1→T2→T3 chain against Mock ATS |
| `tests/integration/test_browser_use_mock.py` | Browser Use agent against local mock server |
| `tests/integration/test_captcha_flow.py` | CAPTCHA detect → solve → verify chain |
| `tests/integration/test_auth_flow.py` | Login → 2FA → session validation |

### 7.3 Mock ATS Server Enhancements

Current: `tests/fixtures/mock_ats_server.py` — basic form submission mock.

**Add**:

```python
# New mock endpoints for testing

# 1. Multi-step form (like Workday)
@app.post("/mock/workday/apply")
async def mock_workday_apply(step: int):
    if step == 1: return {"page": "personal_info", "fields": [...]}
    if step == 2: return {"page": "experience", "fields": [...]}
    if step == 3: return {"page": "questions", "questions": [...]}
    if step == 4: return {"page": "review", "confirmation": "MOCK-CONF-123"}

# 2. CAPTCHA-protected page
@app.get("/mock/captcha-portal")
async def mock_captcha_page():
    return "<div class='cf-turnstile' data-sitekey='test'></div>"

# 3. Login-required page
@app.get("/mock/protected-job")
async def mock_protected_job(session=Depends(verify_session)):
    return "<form>...</form>"

# 4. Dynamic DOM (tests Browser Use's adaptability)
@app.get("/mock/dynamic-portal")
async def mock_dynamic_portal():
    # Randomized field IDs/names each request
    field_id = f"field_{random.randint(1000, 9999)}"
    return f"<form><input id='{field_id}' name='first_name'></form>"

# 5. Confirmation page variants
@app.get("/mock/confirmation/{type}")
async def mock_confirmation(type: str):
    if type == "greenhouse": return "<div>GH-CONF-ABC123</div>"
    if type == "lever": return "<div>Application submitted!</div>"
    if type == "generic": return "<div>Thank you for applying</div>"
```

### 7.4 Browser Use Agent Testing Pattern

```python
# tests/integration/test_browser_use_mock.py

import pytest
from unittest.mock import AsyncMock, patch

from src.pipeline.4_submission.browser_use_agent import (
    BrowserUseSubmissionAgent,
    SubmissionTask,
)

@pytest.fixture
def sample_task():
    return SubmissionTask(
        job_url="http://localhost:8080/mock/greenhouse-job",
        company="TestCorp",
        title="Software Engineer",
        portal_type="greenhouse",
        profile={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "+1234567890",
        },
        resume_pdf_path="./tests/fixtures/test_resume.pdf",
    )

@pytest.mark.asyncio
async def test_browser_use_success(sample_task):
    """Test successful submission via Browser Use."""
    with patch("browser_use.Agent") as MockAgent:
        mock_agent = AsyncMock()
        mock_agent.run.return_value = {
            "success": True,
            "confirmation_id": "MOCK-CONF-123",
        }
        MockAgent.return_value = mock_agent
        
        agent = BrowserUseSubmissionAgent()
        result = await agent.submit(sample_task)
        
        assert result.success is True
        assert result.confirmation_id == "MOCK-CONF-123"
        assert result.tier_used == "T2"

@pytest.mark.asyncio
async def test_browser_use_timeout(sample_task):
    """Test timeout handling."""
    sample_task.timeout_seconds = 1
    
    with patch("browser_use.Agent") as MockAgent:
        mock_agent = AsyncMock()
        mock_agent.run.side_effect = asyncio.TimeoutError()
        MockAgent.return_value = mock_agent
        
        agent = BrowserUseSubmissionAgent()
        result = await agent.submit(sample_task)
        
        assert result.success is False
        assert "timed out" in result.error_message

@pytest.mark.asyncio
async def test_browser_use_fallback_llm(sample_task):
    """Test fallback LLM activation on primary failure."""
    # ... test fallback_llm param is passed correctly
```

### 7.5 Test Pyramid

```
         ┌──────────┐
         │ E2E (5)  │  Full pipeline: discover → evaluate → tailor → submit
         │          │  Against mock ATS server + mock LLM
         ├──────────┤
         │ Integ    │  Browser Use + Mock ATS, routing, captcha, auth
         │  (20)    │  
         ├──────────┤
         │ Unit     │  Agent wrapper, controller actions, routing,
         │  (50+)   │  session validator, credential vault, captcha solver
         └──────────┘
```

---

## Appendix A: File Inventory (New + Modified)

### New Files

| Path | Purpose | Status |
|------|---------|--------|
| `src/pipeline/4_submission/browser_use_agent.py` | Browser Use wrapper + CareerGraphController | ✅ P2a |
| `src/pipeline/4_submission/submission_audit.py` | Audit logger (SQLite + SSE broadcast) | ✅ P2a |
| `tests/unit/test_browser_use_agent.py` | Agent wrapper unit tests | ✅ P2a |
| `tests/unit/test_submission_audit.py` | Audit logger unit tests | ✅ P2a |
| `src/pipeline/4_submission/routing_engine.py` | T1/T2/T3 tier selection logic | P2b |
| `src/pipeline/4_submission/session_validator.py` | Cookie/session pre-flight check | P2b |
| `src/pipeline/4_submission/captcha_solver.py` | CapSolver/2Captcha API integration | P2d |
| `src/core/credentials/vault.py` | OS keyring credential store | ✅ P2c |
| `src/core/credentials/totp.py` | TOTP 2FA code generation | P3b |
| `src/pipeline/4_submission/stealth/behavioral.py` | Bézier mouse + Poisson typing | P3a |
| `tests/unit/test_routing_engine.py` | Unit tests | P2b |
| `tests/unit/test_session_validator.py` | Unit tests | P2b |
| `tests/integration/test_browser_use_mock.py` | Integration tests | P2b |

### Modified Files

| Path | Change |
|------|--------|
| `src/pipeline/4_submission/submitter_engine.py` | Wire T1 FastPath + T2 BrowserUse + T3 WebSurfer |
| `src/pipeline/state_machine.py` | Fix `submit()` call (pass profile+artifacts); raise circuit breaker to 180s |
| `src/pipeline/4_submission/adapters/__init__.py` | Add WorkdayAgenticSubmitter to ATS_ADAPTERS |
| `src/pipeline/4_submission/browser_manager.py` | Swap Playwright → Patchright |
| `src/core/config.py` | Add 20+ new settings |
| `requirements.txt` | Add browser-use, patchright, keyring, pyotp, capsolver |
| `.env.example` | Add new env vars |
| `tests/fixtures/mock_ats_server.py` | Add multi-step, captcha, dynamic DOM, login endpoints |

---

## Appendix B: Decision Log

| Decision | Chosen | Rejected | Rationale |
|----------|--------|----------|-----------|
| BU integration scope | Complement (T2 tier) | Replace Stage 4 | FastPath is faster/cheaper for known ATS; BU for novel DOMs only |
| Browser backend | Patchright (Playwright fork) | Raw Playwright + stealth | playwright-stealth broken since mid-2025; Patchright fixes TLS/HTTP2 fingerprinting |
| CAPTCHA solving | CapSolver API | HITL-only | 60s HITL timeout exceeds circuit breaker; automated solving is 30s max |
| Credential storage | OS keyring | Env vars / SQLite | Passwords in checkpoints.db is a critical security bug; keyring is encrypted at rest |
| LLM for BU | Alibaba Qwen (existing) | ChatBrowserUse | Reuse existing API key + routing; no new vendor dependency |
| Anti-detection | Behavioral simulation | Extension-based | LinkedIn scans 6000+ extensions; behavioral patterns harder to detect |
| Circuit breaker budget | 180s (raised from 45s) | Keep 45s | 45s can't fit captcha(30s) + form fill(15s) + submit(5s); 180s covers worst case |
| WebSurfer future | T3 fallback only | Decommission | Rule-based fallback has value when LLM is down; low maintenance cost |

---

## P2c Artifacts: CredentialVault + Config Settings

**Completed**: 2026-08-26

### Files Created
- `src/core/credentials/vault.py` — CredentialVault with 3 backends (keyring, env, file)
- `src/core/credentials/__init__.py` — Package init with public exports
- `tests/unit/test_credential_vault.py` — Unit tests for all 3 backends

### Files Modified
- `src/core/config.py` — Added `credential_backend`, `credential_service_name`, `credential_file_path` settings
- `src/pipeline/4_submission/submitter_engine.py` — Uses CredentialVault via `credential_ref` pattern (reference, not raw credentials in state)

### Config Settings Added
```python
# Credential vault (OS keyring for secure credential storage)
credential_backend: str = "keyring"  # "keyring" | "env" | "file"
credential_service_name: str = "careergraph"
credential_file_path: str = "./data/credentials.json"  # for file backend
```

### Security Design
- **Credentials never persisted to checkpoints** — pipeline state holds only a `credential_ref` (string key), not raw passwords
- **OS keyring default** — uses Windows Credential Manager / macOS Keychain / Linux Secret Service
- **File backend for CI** — `credential_backend=file` uses encrypted JSON (not for production)
- **Env backend for containers** — `credential_backend=env` reads from `CREDENTIAL_{SITE}_{FIELD}` env vars
