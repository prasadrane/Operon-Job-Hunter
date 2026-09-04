"""Import GGUF model into Ollama."""
import argparse
import subprocess
import tempfile
from pathlib import Path


def import_model(gguf_path: str, model_name: str = "career-brain", modelfile=None):
    gguf_path = Path(gguf_path).resolve()
    if not gguf_path.exists():
        raise FileNotFoundError(f"GGUF file not found: {gguf_path}")

    if modelfile is not None:
        modelfile = Path(modelfile).resolve()
        if not modelfile.exists():
            raise FileNotFoundError(f"Modelfile not found: {modelfile}")
        cmd = ["ollama", "create", model_name, "-f", str(modelfile)]
        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        print(f"Model '{model_name}' imported from {modelfile.name}!")
        return

    # Create Modelfile
    modelfile_content = f"""FROM {gguf_path}
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_predict 512
SYSTEM You are Alex Rivera, a software engineer with 10+ years of experience. Answer in first person.
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".modelfile", delete=False) as f:
        f.write(modelfile_content)
        modelfile_path = f.name

    cmd = ["ollama", "create", model_name, "-f", modelfile_path]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"Model '{model_name}' imported to Ollama!")

    # Cleanup
    Path(modelfile_path).unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gguf", required=True)
    parser.add_argument("--name", default="career-brain")
    parser.add_argument("--modelfile", default=None)
    args = parser.parse_args()
    import_model(args.gguf, args.name, modelfile=args.modelfile)
