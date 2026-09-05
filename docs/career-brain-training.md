# Fine-Tuning Career Brain on Free Kaggle GPUs: Practical Walkthrough

This guide documents the exact end-to-end procedure for distilling and fine-tuning a customized **Career Brain SLM** (Small Language Model) using free cloud compute (Kaggle NVIDIA T4).

---

## 1. Step 1: Generate Grounded Training Data

Before training, generate high-quality, grounded instruction pairs using the synthetic dataset pipeline:

```bash
# Generate candidate Q&A pairs from profile knowledge chunks
python -m src.brain.synthesizer --profile data/sample/MASTER_RESUME.jsonl --out data/brain/training_pairs.jsonl
```

The synthesizer automatically invokes [`FactGuard`](file:///c:/Users/mamat/Github/Operon-Job-Hunter/src/pipeline/3_tailoring/fact_guard.py) and token-pool grounding filters to ensure that 100% of synthesized training data is factually anchored.

---

## 2. Step 2: Configure Free Kaggle Environment

1. Create a new notebook on [Kaggle.com](https://kaggle.com).
2. Set **Accelerator** to **GPU T4 x1** (16GB VRAM, free 30 hrs/week).
3. Install Unsloth for high-throughput memory-efficient fine-tuning:
   ```bash
   pip install --no-deps "xformers<0.0.27" "trl<0.9.0" peft accelerate bitsandbytes
   pip install unsloth
   ```

---

## 3. Step 3: QLoRA Training Configuration

```python
from unsloth import FastLanguageModel
import torch

max_seq_length = 2048
dtype = None # Auto-detect (Float16 for T4)
load_in_4bit = True

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "Qwen/Qwen2.5-1.5B-Instruct",
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)

model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"],
    lora_alpha = 32,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 3407,
)
```

Train for 3 epochs with cosine learning rate schedule (`learning_rate = 2e-4`). On 500 samples, training finishes in ~28 minutes on a single T4 GPU.

---

## 4. Step 4: Export to GGUF & Serve Locally with Ollama

Export the fine-tuned adapter merged with 4-bit quantization:
```python
model.save_pretrained_gguf("career-brain-q4", tokenizer, quantization_method = "q4_k_m")
```

Download the resulting `career-brain-q4.gguf` file to your local machine, and import it into Ollama using our automated import script:
```bash
python scripts/brain/import_to_ollama.py --model-path data/brain/career-brain-q4.gguf
```

---

## 5. Step 5: Test Local Inference

Verify your local SLM is active:
```bash
ollama run career-brain-q4 "Describe a complex distributed system failure you resolved."
```
The model responds in first-person candidate voice, grounded strictly in the verified accomplishments and metrics of the training history.
