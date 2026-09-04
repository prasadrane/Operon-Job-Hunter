# CareerGraph-AI Offline Portfolio Demo

This repository includes a completely self-contained offline demonstration mode. You can test and inspect the full autonomous 5-stage job search, evaluation, tailoring, and submission pipeline **without requiring any external API keys, browser automation dependencies, or paid services**.

---

## Fictional Sample Persona & Data

To ensure privacy and maintain a safe public showcase:
- **Candidate Persona:** Fictional engineer **Alex Rivera** (Seattle, WA), a Senior Backend / Platform Engineer with 6+ years of experience in Python, FastAPI, PostgreSQL, Redis, Kafka, and AWS.
- **Seeded Jobs:** 20 realistic fictional tech roles across fictional companies (Vertexa, Cloudhaven, Datawheel, etc.) spanning backend, platform, data infrastructure, and edge cases (ghost jobs, non-sponsoring roles).
- **Offline Mock LLM:** A deterministic rule-based LLM provider evaluates keyword overlap, generates ATS resumes, drafts cover letters, and flags suspicious postings.

---

## Quickstart Prerequisites

1. Python 3.10+ installed.
2. Dependencies installed:
   ```bash
   pip install -r requirements.txt
   ```
3. No `.env` configuration or API credentials needed for offline demo mode!

---

## Running the Demo

### 1. Standard Offline Demo (Stages 1 through 3)
Run the pipeline on the top jobs using a fresh, throwaway SQLite database:
```bash
python -m src.interface.cli.main demo --jobs 3 --fresh-db
```
What this does:
1. Seeds 20 fictional job postings into `./data/demo/careergraph_demo.db`.
2. Evaluates candidate fit via the 7-Block rubric (Skills match, Seniority, Work authorization, Ghost-job detection).
3. Executes GraphRAG resume tailoring and artifact generation for qualifying roles.
4. Persists the evaluation results and prints stage summaries to the console.

### 2. End-to-End Demo with Mock ATS Submission (Stages 1 through 4)
To test automated application submission, launch with `--with-submit`:
```bash
python -m src.interface.cli.main demo --jobs 3 --with-submit --fresh-db
```
What this does:
1. Boots an ephemeral, in-process mock ATS server (simulating Greenhouse and Lever application portals).
2. Seeds jobs targeting the local mock ATS endpoints.
3. Automatically executes persistent form automation in dry-run mode and captures receipt confirmation IDs.

---

## Exploring Mission Control UI

You can inspect the generated results in the interactive FastAPI / Streamlit Mission Control interface:
```bash
python -m src.interface.cli.main ui
```
Open your browser to [http://localhost:8000](http://localhost:8000) to view:
- **Pipeline Kanban & Ledger:** Live statuses from Discovered to Tailored and Applied.
- **7-Block Evaluation Breakdown:** Detailed rubric scores, gap analyses, and ghost job legitimacy checks.
- **Tailored PDF Resumes & Cover Letters:** Download and view generated PDF artifacts.

---

## Switching to Real LLM Providers

If you wish to run the pipeline with live AI models (e.g. Alibaba DashScope / Qwen, Google Gemini, or OpenRouter):
1. Copy `.env.example` to `.env`.
2. Configure your API keys:
   ```dotenv
   PRIMARY_LLM_PROVIDER=alibaba
   ALIBABA_API_KEY=your_dashscope_api_key_here
   ```
3. To customize the candidate profile with your own background, point `PROFILE_DATA_DIR` to a private directory containing your `MASTER_RESUME.md`:
   ```dotenv
   PROFILE_DATA_DIR=/path/to/private/profile
   ```

---

## Disclaimer

All candidate identities, employer names, and job postings in this demo mode are entirely fictional. Any resemblance to real persons, living or deceased, or actual companies is purely coincidental.
