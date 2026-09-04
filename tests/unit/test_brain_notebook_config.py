import json
from pathlib import Path

NB = Path("scripts/brain/train_kaggle.ipynb")


def _all_source():
    nb = json.loads(NB.read_text(encoding="utf-8"))
    return "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")


def test_notebook_reads_config_env():
    src = _all_source()
    assert "BRAIN_TRAIN_CONFIG" in src and "yaml.safe_load" in src


def test_notebook_has_val_split_and_early_stop():
    src = _all_source()
    assert "val_split" in src and "train_test_split" in src
    assert "EarlyStoppingCallback" in src and "eval_loss" in src


def test_notebook_lora_from_config():
    src = _all_source()
    assert 'cfg["lora"]' in src or "cfg['lora']" in src


def _data_cell_source():
    nb = json.loads(NB.read_text(encoding="utf-8"))
    for c in nb["cells"]:
        if c["cell_type"] == "code":
            src = "".join(c["source"])
            if "Load training data" in src:
                return src
    raise AssertionError("no data cell found")


def test_notebook_dataset_chosen_by_config_not_glob_order():
    """The data cell must resolve its JSONL from cfg["dataset"] (exact name,
    unique match) — never the legacy training_pairs.jsonl priority glob."""
    src = _data_cell_source()
    assert 'cfg["dataset"]' in src
    assert "want" in src and "FileNotFoundError" in src
    assert "training_pairs.jsonl" not in src.split("Load training data", 1)[1]  # no legacy pin
