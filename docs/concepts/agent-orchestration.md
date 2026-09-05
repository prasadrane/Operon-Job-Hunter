# Multi-Agent DAG Orchestration & Fault Tolerance

## 1. The Challenge

Autonomous agentic pipelines that span multi-step workflows - from job discovery and rubric evaluation to GraphRAG resume compilation and browser-based application submission - face fundamental distributed systems challenges:

1. **Cascading Failures & Timeouts:** An unresponsive external LLM provider or hanging browser page load can stall an entire pipeline thread indefinitely.
2. **State Corruption & Lost Progress:** If an application crashes halfway through an evaluation or submission loop, re-running the entire workflow from scratch is wasteful, expensive, and risks duplicate submissions.
3. **Safety & Compliance Boundaries:** Full autonomy without Human-in-the-Loop (HITL) review introduces significant operational risks (e.g., submitting hallucinated claims or applying to scam listings).
4. **Concurrency & Thread Isolation:** Evaluating dozens of jobs concurrently requires thread-safe state persistence without thread-lock deadlocks.

---

## 2. Architectural Pattern

Operon Job Hunter solves these challenges using a **StateGraph Directed Acyclic Graph (DAG)** built on **LangGraph**, complemented by:
- **Thread-Scoped SQLite WAL Checkpointing:** Every pipeline node transition commits a snapshot of the execution state to disk under a dedicated thread ID (`job_id`).
- **Circuit-Breaker Protected Nodes:** Every DAG node execution is wrapped in a decorator that enforces a strict 45-second execution timeout and catches unhandled exceptions before they crash the graph.
- **Explicit Interrupt Gates (`interrupt_before`):** Critical operational thresholds (such as automated submission) pause execution and yield control back to the operator for HITL approval.
- **TypedDict State Reducers:** Execution state is passed across nodes via strongly typed schemas with immutable state merging.

```
                  ┌───────────────────────┐
                  │      eval_node        │
                  │ (Rubric & Ghost Check)│
                  └──────────┬────────────┘
                             │
                  [ Conditional Edge ]
                  fit_score >= 85 & safe?
                    /                 \
            YES   /                     \  NO
                 v                       v
      ┌───────────────────────┐       ┌───────────────────────┐
      │      tailor_node      │       │       END (Drop)      │
      │ (GraphRAG & ATS PDF)  │       └───────────────────────┘
      └──────────┬────────────┘
                 │
         [ interrupt_before ]  <--- Human-in-the-Loop Gate
                 │
                 v
      ┌───────────────────────┐
      │      submit_node      │
      │ (Playwright Submitter)│
      └──────────┬────────────┘
                 │
                 v
      ┌───────────────────────┐
      │      END (Done)       │
      └───────────────────────┘
```

---

## 3. Implementation in Operon Job Hunter

### 3.1. Pipeline DAG Definition
In [`src/pipeline/state_machine.py`](file:///c:/Users/mamat/Github/Operon-Job-Hunter/src/pipeline/state_machine.py), the workflow compiles three core nodes with conditional routing:

```python
workflow = StateGraph(PipelineGraphState)
workflow.add_node("eval_node", with_circuit_breaker()(node_discover_and_evaluate))
workflow.add_node("tailor_node", with_circuit_breaker()(node_graphrag_tailor))
workflow.add_node("submit_node", with_circuit_breaker(timeout_seconds=180.0)(node_submit_and_verify))

workflow.set_entry_point("eval_node")
workflow.add_conditional_edges(
    "eval_node",
    route_evaluation,
    {"tailor_node": "tailor_node", "end_node": END},
)
workflow.add_edge("tailor_node", "submit_node")
workflow.add_edge("submit_node", END)

# Compile graph with persistence and HITL pause before submit
app = workflow.compile(checkpointer=memory, interrupt_before=["submit_node"])
```

### 3.2. Circuit-Breaker Fault Isolation
The `with_circuit_breaker` decorator wraps each node execution in a thread pool executor with an enforceable timeout:
```python
def with_circuit_breaker(timeout_seconds: float = 45.0):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(state: PipelineGraphState) -> Dict[str, Any]:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(fn, state)
                try:
                    return future.result(timeout=timeout_seconds)
                except concurrent.futures.TimeoutError:
                    log.error("Circuit breaker tripped: %s timed out after %ss", fn.__name__, timeout_seconds)
                    return {"current_stage": "FAILED", "error_trace": "Node timeout"}
        return wrapper
    return decorator
```

### 3.3. Thread-Scoped SQLite WAL Checkpointing
Rather than requiring heavy external state brokers (like Redis or PostgreSQL) for local operation, [`src/core/db/checkpointer.py`](file:///c:/Users/mamat/Github/Operon-Job-Hunter/src/core/db/checkpointer.py) provides a thread-safe SQLite checkpointer operating in Write-Ahead Logging (WAL) mode. Each job execution runs under its own isolated `thread_id=job.id`, allowing jobs to pause, recover, or re-run independently.

---

## 4. Architectural Tradeoffs & Lessons Learned

| Decision | Tradeoff Accepted | Alternative Considered | Rationale |
|---|---|---|---|
| **SQLite WAL over PostgreSQL** | Limited to single-machine concurrency (max ~8 workers). | Redis or PostgreSQL state store | Eliminates infrastructure dependencies for the portfolio demo, local CLI, and CI while maintaining full ACID isolation. |
| **Circuit Breakers over Exponential Retries** | Errant API calls fail fast into a fallback queue rather than blocking subsequent jobs. | Multi-tier retry loops | LLM rate limits and hung Playwright pages can tie up worker threads for minutes; failing fast to the next job preserves overall batch throughput. |
| **`interrupt_before` HITL Gates** | Requires operator interaction to trigger submission. | 100% autonomous unattended submission | In high-stakes enterprise applications, human review of tailored artifacts prevents accidental spamming or submission of outdated credentials. |
