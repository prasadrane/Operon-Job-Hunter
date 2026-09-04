"""Convert HF model to GGUF format using llama.cpp."""
import argparse
import subprocess
import sys
from pathlib import Path


def convert(input_dir: str, output_file: str):
    # Find llama.cpp convert script
    convert_script = Path("llama.cpp/convert_hf_to_gguf.py")
    if not convert_script.exists():
        print("ERROR: llama.cpp not found. Clone it first:")
        print("  git clone https://github.com/ggerganov/llama.cpp")
        sys.exit(1)

    cmd = [
        sys.executable, str(convert_script),
        input_dir,
        "--outfile", output_file,
        "--outtype", "f16",
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"GGUF saved to: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="HF model directory")
    parser.add_argument("--output", required=True, help="Output GGUF file")
    args = parser.parse_args()
    convert(args.input, args.output)
