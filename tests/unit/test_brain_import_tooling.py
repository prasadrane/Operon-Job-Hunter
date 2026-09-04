import importlib
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path("scripts/brain")))
imp = importlib.import_module("import_to_ollama")


def test_modelfile_path_used_when_given(tmp_path):
    gguf = tmp_path / "base.gguf"; gguf.write_bytes(b"x")
    mf = tmp_path / "Modelfile.tailor"; mf.write_text("FROM base\nADAPTER lora.gguf\n")
    with patch.object(imp.subprocess, "run") as run:
        imp.import_model(str(gguf), "career-brain-tailor-v1", modelfile=mf)
    cmd = run.call_args[0][0]
    assert cmd[:2] == ["ollama", "create"] and str(mf) in cmd


def test_legacy_inline_modelfile_still_works(tmp_path):
    gguf = tmp_path / "base.gguf"; gguf.write_bytes(b"x")
    with patch.object(imp.subprocess, "run"):
        imp.import_model(str(gguf), "career-brain")  # no modelfile arg
