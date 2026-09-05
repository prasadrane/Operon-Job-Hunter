# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Code Navigation - Use Graph Tools First

This repo has **graphify** and **codebase-memory-mcp** indexed. Before manually reading files to understand structure, callers, or dependencies:

1. **Use `search_graph`** to find symbols, functions, classes by name or semantic query
2. **Use `trace_path`** to follow call chains (callers/callees) and data flow
3. **Use `get_code_snippet`** to retrieve exact source for a qualified name
4. **Use `query_graph`** for complex multi-hop patterns (Cypher queries)
5. **Use `get_architecture`** for high-level system overview and cluster analysis
6. **Use graphify** (`graphify-out/` directory) for community-detected knowledge graphs with BFS/DFS query tools

Only fall back to manual file reading (Read/Grep) when graph coverage is insufficient or you need to inspect implementation details not captured in the graph.

## Project Overview

Operon Job Hunter is an autonomous agentic platform for job search automation. It implements a 5-stage pipeline: Discovery → Evaluation → Tailoring → Submission → Lifecycle. The system uses LangGraph StateGraph for orchestration, a 3-tier memory architecture (Core/Recall/Archival), and supports multiple LLM providers (Alibaba Qwen as primary, Gemini/OpenRouter as fallback).

## Common Commands

### Testing
```bash
# Run all unit tests (416 tests)
python -m pytest tests/unit/ -v

# Run specific test file
python -m pytest tests/unit/test_config_models.py -v

# Run integration tests
python -m pytest tests/integration/ -v

# Run with coverage
python -m pytest tests/unit/ --cov=src --cov-report=html
```

### CLI Commands
```bash
# Launch Mission Control Web UI (http://localhost:8000)
python -m src.interface.cli.main ui

# Run full end-to-end pipeline for a job
python -m src.interface.cli.main run <JOB_ID>

# Stage-specific commands
python -m src.interface.cli.main scan                    # Stage 1: Discovery
python -m src.interface.cli.main ingest <URL>            # Stage 1: Single job ingest
python -m src.interface.cli.main evaluate <JOB_ID>       # Stage 2: 7-Block evaluation
python -m src.interface.cli.main tailor <JOB_ID>         # Stage 3: GraphRAG tailoring
python -m src.interface.cli.main submit <JOB_ID>         # Stage 4: Playwright submission
python -m src.interface.cli.main submit <JOB_ID> --dry-run

# Background services
python -m src.interface.cli.main daemon --interval 300   # Scheduled crawler + Gmail sync
python -m src.interface.cli.main status                  # Live pipeline summary
```

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium

# Configure environment (copy and edit)
cp .env.example .env
```

## Architecture Overview

### 5-Stage Pipeline Architecture

The pipeline is orchestrated via LangGraph StateGraph (`src/pipeline/state_machine.py`) with thread-scoped SQLite WAL checkpoints:

1. **Stage 1 - Discovery** (`src/pipeline/1_discovery/`): 9 concurrent crawlers (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Amazon, Google, Microsoft, EchoJobs) with deferred tool search. Includes H-1B sponsorship verification against USCIS datasets.

2. **Stage 2 - Evaluation** (`src/pipeline/2_evaluation/`): 7-block rubric scorer evaluating tech stack overlap, seniority fit, compensation, pitch angles, STAR mappings. Multi-model consensus voting prevents false rejections. Ghost job detector filters stale/scam postings.

3. **Stage 3 - Tailoring** (`src/pipeline/3_tailoring/`): Multi-hop GraphRAG retrieval from NetworkX career knowledge graph. Evaluator-Optimizer loop (Recruiter, Hiring Manager, ATS Specialist personas) with surgical delta patching. Deterministic PDF compiler (ReportLab/Typst) with <20% bold cap validation.

4. **Stage 4 - Submission** (`src/pipeline/4_submission/`): 3-tier submission architecture: (T1) FastPath deterministic DOM autofill with ordered selector tuples + self-healing for standard profile fields across all portals, (T2) Browser Use Agent (LLM-driven via `browser_use.Agent`) for unknown/generic portals with dynamic DOMs, (T3) WebSurfer Agent (AXTree + Set-of-Marks visual grounding) as rule-based fallback. ATS-specific adapters (Greenhouse, Lever, Ashby, WorkdayAgentic multi-step wizard, Generic) for platform-specific form handling. CredentialVault (`src/core/credentials/vault.py`) stores portal credentials in OS keyring (configurable: keyring/env/file backends via `CREDENTIAL_BACKEND`). Pipeline state carries only `credential_ref` (a string key reference) - raw credentials are never persisted to checkpoints. Submission audit logger (`submission_audit.py`) tracks every browser action to SQLite `submission_audit_log` table for observability and lifecycle learning. 180-second circuit breaker on submit_node. Kill switch: `SUBMISSION_BROWSER_USE_ENABLED=false`. Candidate profile and tailored artifacts passed through from pipeline state.

5. **Stage 5 - Lifecycle** (`src/pipeline/5_lifecycle/`): Gmail watcher monitors confirmation receipts and status changes. OA Radar tracks online assessments. Retrospective agent analyzes outcomes.

### State Machine & Checkpointing

`PipelineGraphState` (TypedDict with operator reducers) ensures thread-safe concurrent state transitions. The `with_circuit_breaker` decorator enforces 45-second execution budgets per node. Checkpoints persist to SQLite WAL by default (configurable to memory/postgres via `CHECKPOINTER_DRIVER` env var).

### 3-Tier Memory Hierarchy

- **Core Memory** (in-context RAM): Working set for active pipeline execution
- **Recall Memory** (SQLite ledger): Transaction log with WAL checkpoints (`data/careergraph.db`)
- **Archival Memory** (NetworkX GraphRAG): Career knowledge graph storing causal project chains and STAR narratives

### LLM Gateway & Multi-Provider Routing

`src/core/gateway/` implements tiered model routing:
- Primary: Alibaba Qwen (qwen3.6-flash via token-plan API)
- Fallback: Gemini 2.5 Flash/Pro, OpenRouter
- Rate limit detection and automatic retry logic in `base.py`

### Web Interface

FastAPI REST + SSE endpoints (`src/interface/api/routes.py`) serve Mission Control 2.0 web UI (`web/`). Server-Sent Events stream real-time pipeline state updates. D3.js visualizes the career knowledge graph.

### Browser Automation

Playwright with stealth plugin (`playwright-stealth`) for persistent browser sessions. Browser profiles stored in `data/browser_profile/`. Form healing engine handles dynamic DOM changes. Captcha handler integrates with external solving services.

### Career Brain (Fine-Tuned Local LLM)

`src/brain/` implements a fine-tuned Qwen3-1.7B "Career Brain" that runs locally via Ollama, grounded in GraphRAG retrieval from MASTER_RESUME.jsonl. Three inference modes: avatar (first-person career Q&A), tailoring (resume/cover letter optimization), qa (general knowledge). Mode router classifies queries automatically. FactGuard verification on all responses. Falls back to LLM gateway (Alibaba Qwen) when Ollama unavailable. Training via QLoRA on Kaggle T4 (free). See `docs/brain-usage.md` for quick start guide.

### Multi-Agent Platform (P5)

`src/agents/` hosts reactive agents on the core domain bus (`src/core/events/`, bridged into the Mission Control SSE stream via `install_sse_bridge`): `discovery_orchestrator` (drives `JobScanner`, emits `JOB_DISCOVERED`), `application_agent` (wraps `BatchPipelineDispatcher.process_single_job` off-thread on discovery; submission stays gated by the LangGraph `interrupt_before=["submit_node"]` HITL - resume only via `mission resume`), `networking_agent` (LLM-drafted outreach; requires a resolved approval row before any LinkedIn send). Every decision lands in the `agent_decisions` SQLite table (`src/core/telemetry/agent_ledger.py`); `PipelineGraphState` carries append-only `agent_decisions`/`integration_results` keys; stage introspection via `src/core/stages/stage_registry.py`. `src/integrations/` holds read-only ATS board API enrichment (`ats_readonly.py` - no public ATS API allows application submission) and LinkedIn automation via Patchright (`linkedin/`) behind three mandatory gates: `LINKEDIN_ENABLED` (default false), `LinkedInActionBudget` (SQLite daily caps), `LinkedInApprovalGate` (`linkedin_approvals` table). New API-backed boards: `remote_boards.py` (Remotive, Adzuna). CLI: `python -m src.interface.cli.main mission start|scan|status|approvals list|approvals approve <id>|resume <JOB_ID>`.

## Key Configuration

Settings loaded via Pydantic from environment variables (see `src/core/config.py`):
- `PRIMARY_LLM_PROVIDER`: alibaba | gemini | openrouter
- `MIN_FIT_SCORE`: Threshold for pipeline progression (default 72.0)
- `CHECKPOINTER_DRIVER`: sqlite | memory | postgres
- `PDF_COMPILER_BACKEND`: reportlab | typst
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: For mobile HITL approvals
- `LINKEDIN_ENABLED` (default false) / `LINKEDIN_AUTO_APPROVE` (false) / `LINKEDIN_DAILY_*` caps: P5 LinkedIn automation gates
- `AUTO_SUBMIT_ENABLED` (false): policy flag; resumes only ever happen through `mission resume`
- `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`: P5b Adzuna feeder (no-ops unset)

## Testing Patterns

Tests use pytest-asyncio with `asyncio_mode = "auto"`. Mock ATS server in `tests/fixtures/mock_ats_server.py` for submission testing. Unit tests isolate individual pipeline stages; integration tests verify end-to-end flows including checkpoint recovery.

## Data Directory Structure

- `data/careergraph.db`: SQLite database (jobs, evaluations, applications)
- `data/checkpoints.db`: LangGraph checkpoint storage
- `data/browser_profile/`: Persistent Playwright browser state
- `data/artifacts/`: Generated resumes, cover letters, PDFs
- `data/h1b_sponsors.json`: USCIS verified sponsor dataset
- `data/companies.yaml`: Watchlist company configuration
- `data/MASTER_RESUME.md`: Candidate career source of truth
