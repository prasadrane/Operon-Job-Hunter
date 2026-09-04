# Career Brain Usage Guide

## Quick Start

1. Ensure Ollama is running: `ollama serve`
2. Import the model: `python scripts/brain/import_to_ollama.py --gguf data/brain/career-brain-1.7b-q4.gguf`
3. Query: `python -m src.interface.cli.main brain query "Tell me about your Kafka experience"`

## API

POST /brain/query
GET /brain/status
GET /brain/models

## Training

1. Generate training data: `python -m src.interface.cli.main brain synthesize`
2. Upload to Kaggle and run `scripts/brain/train_kaggle.ipynb`
3. Download adapter, merge, convert, import:
   python scripts/brain/merge_lora.py --adapter data/brain/career-brain-lora --output data/brain/merged-model
   python scripts/brain/convert_to_gguf.py --input data/brain/merged-model --output data/brain/career-brain.gguf
   llama-quantize data/brain/career-brain.gguf data/brain/career-brain-q4.gguf Q4_K_M
   python scripts/brain/import_to_ollama.py --gguf data/brain/career-brain-q4.gguf
