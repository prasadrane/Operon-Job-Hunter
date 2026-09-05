# GraphRAG & Anti-Hallucination Patterns in Resume Tailoring

## 1. The Challenge of Naive RAG in Professional Profiles

Standard Retrieval-Augmented Generation (RAG) relies on cosine similarity over flat text chunks embedded into vector databases. In resume tailoring and technical evaluation, this naive approach fails in three critical ways:

1. **Loss of Relational Structure:** A vector search for `"high-throughput distributed streaming"` might retrieve a Kafka bullet from Company A and an AWS Lambda bullet from Company B, mixing achievements and fabricating composite timelines.
2. **Metric & Technology Hallucination:** When prompted to "tailor this bullet for a Kubernetes role," general-purpose LLMs routinely invent experience - claiming the candidate migrated clusters or managed Helm charts when their master profile mentions only Docker.
3. **Keyword Stuffing vs. Contextual Grounding:** Generic tailoring models insert keywords at the expense of ATS readability, failing strict page budget constraints and formatting parsers.

---

## 2. Architectural Solution: Knowledge Graph + Multi-Hop GraphRAG

Operon Job Hunter replaces flat text chunking with a **NetworkX-powered Knowledge Graph** (`data/embedded_graph.json`), modeling the candidate's career as a strongly typed entity-relationship graph:

```
 (Company: Helios Commerce)
         │
    [EMPLOYED]
         ▼
  (Role: Senior Platform Engineer)
         │
    [LED_STORY]
         ▼
  (Story: Event Ingestion Pipeline) ───[HAS_ACTION]───► (Action: Re-architected Kafka consumer)
         │                                                      │
    [USED_TECH]                                            [ACHIEVED_METRIC]
         ▼                                                      ▼
  (Tech: Kafka, FastAPI)                               (Metric: 40M events/day, 62% p95 cut)
```

### 2.1. Multi-Hop Relational Retrieval
When tailoring for a target job, the [`HybridGraphRetriever`](file:///c:/Users/mamat/Github/Operon-Job-Hunter/src/pipeline/3_tailoring/hybrid_graph_retriever.py) extracts key requirements from the job posting and traverses the knowledge graph:
1. **Anchor Node Matching:** Identifies candidate technologies matching the job's core stack.
2. **Neighbor Expansion (1-2 Hops):** Retrieves the parent `STAR_Story`, the associated `Action`, the verified `ImpactMetric`, and the corresponding `Company`.
3. **Provenance Binding:** Ensures that metrics are never detached from the specific role and timeframe where they occurred.

---

## 3. FactGuard: Anti-Hallucination Verification

Before any tailored bullet is compiled into a PDF artifact, it must pass through [`FactGuard`](file:///c:/Users/mamat/Github/Operon-Job-Hunter/src/pipeline/3_tailoring/fact_guard.py), a deterministic integrity validator:

```python
class FactGuard:
    """Deterministic validator for career claim factual integrity."""

    def validate_bullet(self, bullet_text: str, company: Optional[str] = None) -> Tuple[bool, str]:
        # 1. Unverified Technology Check
        for pat in self.unverified_patterns:
            if pat.search(bullet_text):
                return False, f"Detected unverified claim: {pat.pattern}"

        # 2. Metric Inflation & Verification Check
        metrics = self._extract_metrics(bullet_text)
        for m in metrics:
            if m.lower() not in self.verified_metrics:
                return False, f"Unverified metric detected: {m}"

        return True, "Factual integrity verified"
```

If the LLM introduces unverified frameworks (e.g. Solidity, Rust) or inflated metrics that lack grounding in the candidate's knowledge graph, `FactGuard` rejects the generation and falls back to the canonical verified bullet.

---

## 4. Evaluator-Optimizer Feedback Loop

In Stage 3 tailoring, the system implements an **Evaluator-Optimizer loop**:
1. **Generator Node:** Proposes tailored summary and role bullets optimized for the JD keywords.
2. **FactGuard Node:** Evaluates factual grounding and semantic equivalence.
3. **ReportLab ATS Compiler:** Enforces strict page budgeting (1-page or 2-page hard ceiling). If text overflows the layout budget, an adaptive compaction loop trims lower-priority proof points until the PDF fits the target budget exactly.

---

## 5. Tradeoffs & Lessons Learned

| Decision | Tradeoff Accepted | Alternative Considered | Rationale |
|---|---|---|---|
| **NetworkX in-memory graph vs Neo4j** | Graph size limited to candidate career scope (~5,000 nodes/edges). | External Neo4j instance | A single candidate's career fits entirely in memory; eliminating external graph DBs removes operational overhead and enables sub-millisecond traversal. |
| **Strict Reject-on-Hallucination** | Occasionally rejects creative phrasings that use unlisted synonyms. | Soft penalty scoring | Zero-tolerance for false claims is essential in professional recruitment; unverified claims risk immediate candidate disqualification in background checks. |
| **Programmatic ATS Page Budgets** | Requires dynamic font and spacing adjustments. | Fixed template layouts | Rigid templates either spill onto an orphan second page (a severe ATS penalty) or leave awkward blank whitespace. Adaptive compaction guarantees pixel-perfect layout every time. |
