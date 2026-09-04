"""Merge LoRA adapter into base model."""
import argparse
from pathlib import Path


def merge(base_model: str, adapter_path: str, output_path: str):
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"Loading base model: {base_model}")
    model = AutoModelForCausalLM.from_pretrained(base_model, device_map="cpu")
    tokenizer = AutoTokenizer.from_pretrained(base_model)

    print(f"Loading LoRA adapter: {adapter_path}")
    model = PeftModel.from_pretrained(model, adapter_path)

    print("Merging...")
    model = model.merge_and_unload()

    print(f"Saving to: {output_path}")
    Path(output_path).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)
    print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="Qwen/Qwen3-1.7B")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    merge(args.base, args.adapter, args.output)
