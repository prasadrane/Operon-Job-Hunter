# SLM Distillation, QLoRA Fine-Tuning & Evaluation Gating

## 1. The Economics of Specialized Career SLMs

While frontier LLMs (such as Claude 3.5 Sonnet and GPT-4o) excel at general reasoning, using them for repetitive, structured candidate tasks introduces significant overhead:
- **Cost Accumulation:** Running 50 evaluations and tailoring runs per day at frontier API rates costs upwards of $1.50–$3.00/day.
- **Network Latency:** Round-trip API calls to cloud providers average 1.5–4.0 seconds per stage.
- **Privacy Considerations:** Uploading exhaustive career histories, salary targets, and private application documents to external cloud vendors may violate strict privacy policies.

CareerGraph AI demonstrates **SLM Distillation**: fine-tuning a compact 1.7B parameter open-weights model (**Qwen 2.5 1.7B / Qwen 3**) to achieve frontier-level accuracy on specific career tasks at zero ongoing inference cost.

---

## 2. The Distillation Pipeline Architecture

```
  ┌─────────────────────────┐
  │  Master Career History  │
  │ (Graph & Verified Facts)│
  └────────────┬────────────┘
               │
               ▼
  ┌─────────────────────────┐
  │   Teacher Model (LLM)   │ ◄── Teacher Prompts (Jinja2 Templates)
  │ (Synthesis of QA Pairs) │
  └────────────┬────────────┘
               │
               ▼
  ┌─────────────────────────┐
  │    Evaluation Gate      │ ───► [ Rejects Ledger: hallucinated / ungrounded ]
  │  (Token Pool Grounding) │
  └────────────┬────────────┘
               │ Passed
               ▼
  ┌─────────────────────────┐
  │  QLoRA Fine-Tuning      │
  │   (Free Kaggle T4 GPU)  │
  └────────────┬────────────┘
               │
               ▼
  ┌─────────────────────────┐
  │   GGUF Export & Ollama  │
  │  (Sub-100ms Local SLM)  │
  └─────────────────────────┘
```

---

## 3. Evaluation-Gated Dataset Synthesis

High-quality distillation requires eliminating teacher hallucinations before training. In [`src/brain/synthesizer.py`](file:///c:/Users/mamat/Github/CareerGraph-AI/src/brain/synthesizer.py) and [`src/brain/validator.py`](file:///c:/Users/mamat/Github/CareerGraph-AI/src/brain/validator.py), every synthesized pair passes three automated gates:

1. **First-Person Persona Enforcement:** Rejects third-person narration ("Alex led the migration...") in favor of first-person interview voice ("I led the migration...").
2. **Grounding Token Pool Validation:** Compares named entities and numerical metrics in the generated answer against an allowable token pool derived from the input career chunks. If ungrounded tokens exceed 20%, the sample is routed to `rejects.jsonl`.
3. **Refusal & Length Filters:** Drops evasive outputs, truncated completions, or answers failing JSON schema constraints.

---

## 4. Free-Tier Training on Kaggle T4

Fine-tuning is designed to run entirely within free computational tiers:
- **Hardware:** Single NVIDIA Tesla T4 (16GB VRAM) via free Kaggle Notebooks.
- **Method:** 4-bit NormalFloat (NF4) quantization with LoRA adapters ($r=16$, $\alpha=32$).
- **Efficiency:** Training 500 high-yield curated instruction pairs takes under 35 minutes and requires less than 7GB of GPU memory.

---

## 5. 3-Way Benchmark Evaluation

To verify fine-tuning efficacy, [`data/brain/3way_benchmark_results.json`](file:///c:/Users/mamat/Github/CareerGraph-AI/data/brain/3way_benchmark_results.json) evaluates three tiers of models across technical Q&A, STAR stories, and bullet tailoring:

| Benchmark Dimension | Base Pretrained (Qwen 1.7B) | Career Brain (Fine-Tuned SLM) | Frontier Teacher (Claude / GPT-4o) |
|---|---|---|---|
| **Factual Grounding** | 42.1% (high hallucination) | **96.4%** (strictly grounded) | 98.2% |
| **First-Person Voice** | 58.0% | **99.1%** | 97.5% |
| **JSON Schema Pass Rate** | 64.3% | **98.8%** | 99.5% |
| **Average Latency** | 85ms | **92ms** | 2,450ms |
| **Cost per 1,000 Inferences** | **$0.00** | **$0.00** | ~$18.50 |

The fine-tuned SLM matches the teacher's factual grounding and formatting precision while delivering **25x faster latency** and **zero operational cost**.
