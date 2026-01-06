# Stirling PDF Synthetic Data Generator

Generate synthetic PDFs with realistic data using native Python PDF processing and GitHub Models LLM.

## Features

- ✅ **No Docker required** - Pure Python PDF processing
- ✅ Accepts images, scanned PDFs, and native PDFs
- ✅ Automatic OCR for scanned documents (requires Tesseract)
- ✅ Intelligent variable field detection using LLM
- ✅ Coherent synthetic data generation
- ✅ Vector graphics preservation (lines, rectangles, curves)
- ✅ Optional collision resolution and word spacing

## Prerequisites

- Python 3.10+
- **For OCR** (scanned documents only):
  ```bash
  # macOS
  brew install tesseract ghostscript
  
  # Linux
  apt-get install tesseract-ocr ghostscript
  ```
- GitHub token for LLM (set in `.env`)

## Installation

```bash
cd stirling-pdf-sdg

# Install with uv
uv pip install -e .

# Or with pip
pip install -e .

# Create .env file
cp .env.example .env
# Add your GITHUB_TOKEN to .env
```

## Docker

### Build

```bash
# Using docker-compose (recommended)
docker-compose build

# Or using docker directly
docker build -t stirling-pdf-sdg .
```

### Run with Docker Compose

```bash
# Create data directories
mkdir -p data/input data/output data/cache

# Copy your PDF to input
cp your-document.pdf data/input/

# Run extraction test
docker-compose run stirling-sdg python test_extraction.py /data/input/your-document.pdf -o /data/output

# Run full pipeline with LLM synthesis
docker-compose run stirling-sdg python full_pipeline.py /data/input/your-document.pdf -o /data/output

# Generate multiple variations
docker-compose run stirling-sdg python full_pipeline.py /data/input/your-document.pdf -n 10 -o /data/output
```

### Run with Docker

```bash
docker run -it --rm \
  -v $(pwd)/data/input:/data/input:ro \
  -v $(pwd)/data/output:/data/output \
  -e GITHUB_TOKEN=$GITHUB_TOKEN \
  stirling-pdf-sdg \
  python test_extraction.py /data/input/your-document.pdf -o /data/output
```

### Environment Variables

Set these in your `.env` file (used automatically by docker-compose):

```bash
GITHUB_TOKEN=your_github_token_here
LOG_LEVEL=INFO
OCR_LANGUAGES=eng
```

## Quick Start

### Test PDF Extraction & Reconstruction

```bash
# Basic extraction test
python test_extraction.py input.pdf

# With collision resolution
python test_extraction.py input.pdf --resolve-collisions

# Force OCR on native PDFs
python test_extraction.py input.pdf --force-ocr
```

### Full Pipeline (with LLM synthesis)

```bash
# Process a single document
python full_pipeline.py input.pdf

# Generate 10 variations
python full_pipeline.py input.pdf -n 10

# Skip LLM synthesis (extraction only)
python full_pipeline.py input.pdf --skip-synthesis
```

## SDK Usage

```python
from stirling_sdg import (
    LocalStirlingClient,
    DocumentDetector,
    ContentClassifier,
    SyntheticDataGenerator,
    JSONEditor,
    Settings,
)

# Initialize
settings = Settings()
client = LocalStirlingClient(cache_dir=Path("./cache"))
detector = DocumentDetector()

# Detect document type
doc_type = detector.detect(Path("input.pdf"))  # "digital_pdf", "scanned_pdf", "image"

# Extract PDF to JSON
pdf_json = client.pdf_to_json(Path("input.pdf"))

# Reconstruct PDF from JSON
client.json_to_pdf(
    pdf_json, 
    Path("output.pdf"),
    resolve_collisions=True,  # Optional: fix overlapping text
    add_word_spacing=True,    # Optional: add word spacing
)
```

## Configuration

Edit `.env` file:

```bash
# Required for LLM synthesis
GITHUB_TOKEN=your_github_token_here

# Optional
LLM_MODEL=openai/gpt-4o
OCR_LANGUAGES=eng
LOG_LEVEL=INFO
```

## Project Structure

```
stirling-pdf-sdg/
├── src/stirling_sdg/       # Main SDK package
│   ├── stirling/           # PDF processing (LocalStirlingClient)
│   ├── classification/     # LLM-based field classification
│   ├── synthesis/          # Synthetic data generation
│   ├── json_editor/        # JSON manipulation
│   ├── detection/          # Document type detection
│   └── utils/              # Utilities
├── test_extraction.py      # PDF extraction test script
├── full_pipeline.py        # Full synthesis pipeline
└── test_results/           # Output directory
```

## How It Works

1. **Document Detection**: Detects if input is image, scanned PDF, or native PDF
2. **OCR (if needed)**: Converts scanned documents using ocrmypdf + Tesseract
3. **PDF→JSON**: Extracts text, positions, fonts, and vector graphics using pdfplumber
4. **Classification**: LLM identifies variable vs static text fields
5. **Synthesis**: LLM generates coherent synthetic data
6. **JSON Editing**: Replaces text values in JSON structure
7. **PDF Reconstruction**: Rebuilds PDF using reportlab

## License

MIT License
