# Alex Rivera
Seattle, WA | alex.rivera@example.com | +1 (555) 014-2033

## Summary
Backend/platform engineer with 6+ years building high-throughput event
pipelines and API services in Python (FastAPI, Django). Track record:
40M events/day ingestion platform, payments idempotency rework,
Kubernetes migration, p95 latency cuts. Strong on PostgreSQL, Kafka,
Redis, AWS, Terraform.

## Skills
- Languages: Python, SQL, Go (working knowledge), Bash
- Frameworks: FastAPI, Django, SQLAlchemy, gRPC
- Data & Messaging: PostgreSQL, Redis, Kafka, Elasticsearch
- Infrastructure: AWS (ECS, Lambda, S3, RDS), Kubernetes, Docker, Terraform
- Practices: CI/CD (GitHub Actions), observability (OpenTelemetry, Grafana), TDD

## Experience

### Senior Backend Engineer - Nimbus Analytics
*March 2022 - Present | Seattle, WA*
- Designed and built the event ingestion platform handling 40M events/day (Python, FastAPI, Kafka), cutting p95 ingest latency 62% via backpressure batching and consumer-group rebalancing.
- Led migration of 14 services from ECS to Kubernetes; wrote Terraform modules + rollout tooling, zero-downtime cutover in 6 weeks.
- Introduced contract tests for 9 internal APIs, reducing cross-team integration incidents 45% quarter-over-quarter.
- Mentor 3 engineers; run the platform on-call design review.

### Backend Engineer - Helios Commerce
*June 2019 - February 2022 | Portland, OR*
- Reworked payment-capture flow with idempotency keys (PostgreSQL advisory locks), eliminating duplicate-charge incidents ( since launch vs ~12/quarter).
- Sharded the orders database by merchant_id; p99 query time down 71%.
- Built order-webhooks delivery system (Kafka + Redis retry queues), 99.97% delivered-within-60s.

### Software Engineer - Brightline Labs
*July 2017 - May 2019 | Remote*
- Extracted auth and billing services from Django monolith (strangler pattern), deploy frequency weekly to daily.
- Wrote load-test harness (Locust) that caught two memory leaks pre-launch.

## STAR Stories

### Kafka backpressure outage (Nimbus Analytics)
Situation: Black-Friday spike tripled event rate; consumers lagged 40 minutes.
Task: Restore real-time processing without dropping events.
Action: Added admission-control batching, autoscaled consumer groups on lag metric, shipped priority lanes for paying tenants.
Result: Lag cleared in 18 minutes; no data loss; runbook adopted org-wide.

### Payments idempotency (Helios Commerce)
Situation: Retry storms caused duplicate charges.
Task: Make capture flow exactly-once from the caller's perspective.
Action: Idempotency-key schema, advisory locks, replay-safe state machine, chaos tests with injected retries.
Result: Zero duplicate charges since launch; pattern reused by refunds team.

### Kubernetes migration (Nimbus Analytics)
Situation: ECS deploy times and bin-packing costs growing.
Task: Move 14 services to Kubernetes without downtime.
Action: Terraform base modules, canary pipeline, progressive traffic shifts.
Result: Cutover in 6 weeks; infra cost down 22%; deploys 4x faster.

### Flaky-test turnaround (Brightline Labs)
Situation: CI flake rate ~18%, engineers ignoring failures.
Task: Make main green-trusted again.
Action: Quarantine harness, deterministic time/random fixtures, retry budget.
Result: Flake rate under 1% in one quarter.

## Education
BS Computer Science - Western State University, 2017

## Certifications
- AWS Certified Solutions Architect - Associate (fictional)
