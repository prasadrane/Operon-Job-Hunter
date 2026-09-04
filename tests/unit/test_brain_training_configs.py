# tests/unit/test_brain_training_configs.py
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

TARGETS = {"q_proj", "k_proj", "v_proj", "o_proj",
           "gate_proj", "up_proj", "down_proj"}


@pytest.mark.parametrize("name", ["tailor", "qa"])
def test_config_shape(name):
    cfg = yaml.safe_load(Path(f"data/brain/training_configs/{name}.yaml").read_text(encoding="utf-8"))
    assert cfg["lora"]["r"] == 16 and cfg["lora"]["lora_alpha"] == 32
    assert TARGETS <= set(cfg["lora"]["target_modules"])
    tr = cfg["training"]
    assert tr["num_train_epochs"] <= 4
    assert tr["early_stopping_patience"] >= 1
    assert tr["warmup_ratio"] == pytest.approx(0.03)
    assert tr["max_seq_length"] == 2048 and tr.get("packing", True)
    assert cfg["neftune_noise_alpha"] == 5
    assert cfg["lr_scheduler_type"] == "cosine"
    # T4 bug guard: never bf16-compute + fp16 together (default.yaml disease)
    assert cfg["quantization"]["bnb_4bit_compute_dtype"] == "float32"
    assert tr.get("fp16", False) is False and tr.get("bf16", False) is False
