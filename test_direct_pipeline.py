#!/usr/bin/env python3
"""Test script for direct PDF editing pipeline.

This script tests the new direct editing approach for native PDFs.
It uses PyMuPDF to find and replace text while preserving layout.

Usage:
    python test_direct_pipeline.py <input_pdf> [options]

Examples:
    # Single document
    python test_direct_pipeline.py RESUME.pdf

    # Generate 5 variations
    python test_direct_pipeline.py RESUME.pdf -n 5 -o output/

    # Create template only (no synthesis)
    python test_direct_pipeline.py RESUME.pdf --template-only

    # Use existing template
    python test_direct_pipeline.py RESUME.pdf --template templates/resume_template.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.stirling_sdg import (
    Settings,
    DirectEditClient,
    DocumentDetector,
    ContentClassifier,
    SyntheticDataGenerator,
)
from src.stirling_sdg.utils.logging_utils import setup_logging


def create_template_from_pdf(pdf_path: Path, settings: Settings) -> dict:
    """Extract template from a native PDF using DirectEditClient.

    Args:
        pdf_path: Path to native PDF
        settings: Application settings

    Returns:
        Template dict with variable_fields and metadata
    """
    print(f"\n{'='*60}")
    print("Step 1: Extract Text Elements")
    print("-" * 60)

    with DirectEditClient(pdf_path) as client:
        text_elements = client.extract_text_elements()
        print(f"  Extracted {len(text_elements)} text elements")

        # Build pseudo-JSON for classifier
        pages_data = {}
        for elem in text_elements:
            page_num = elem["page"] + 1
            if page_num not in pages_data:
                pages_data[page_num] = []
            pages_data[page_num].append({
                "text": elem["text"],
                "x": elem["rect"][0],
                "y": elem["rect"][1],
                "width": elem["rect"][2] - elem["rect"][0],
                "height": elem["rect"][3] - elem["rect"][1],
                "fontSize": elem["size"],
                "fontName": elem["font"],
            })

        pdf_json = {
            "pages": [
                {"pageNumber": pn, "textElements": elems}
                for pn, elems in sorted(pages_data.items())
            ]
        }

    print(f"\n{'='*60}")
    print("Step 2: Classify Variable Fields (LLM)")
    print("-" * 60)

    classifier = ContentClassifier(settings)
    template = classifier.classify(pdf_json)

    variable_fields = template.get("variable_fields", [])
    print(f"  Found {len(variable_fields)} variable fields")

    # Enrich template with direct edit metadata
    template["type"] = "direct_edit"
    template["source_file"] = str(pdf_path)

    # Add positional info
    for field in variable_fields:
        field_text = field.get("text", "")
        for elem in text_elements:
            if elem["text"] == field_text:
                field["rect"] = elem["rect"]
                field["font"] = elem["font"]
                field["size"] = elem["size"]
                field["color"] = elem["color"]
                field["page"] = elem["page"]
                break

    if variable_fields:
        print("\n  Variable fields:")
        for field in variable_fields[:10]:
            print(f"    - '{field.get('text', '')[:40]}' → {field.get('fieldType')}")
        if len(variable_fields) > 10:
            print(f"    ... and {len(variable_fields) - 10} more")

    return template


def generate_variation(
    pdf_path: Path,
    template: dict,
    output_path: Path,
    settings: Settings,
    variation_num: int = 1,
) -> Path:
    """Generate a single synthetic variation.

    Args:
        pdf_path: Path to source PDF
        template: Classification template
        output_path: Path for output PDF
        settings: Application settings
        variation_num: Variation number (for logging)

    Returns:
        Path to generated PDF
    """
    print(f"\n{'='*60}")
    print(f"Generating Variation {variation_num}")
    print("-" * 60)

    # Generate synthetic data
    generator = SyntheticDataGenerator(settings)
    synthetic_data = generator.generate(template)
    print(f"  Generated {len(synthetic_data)} synthetic values")

    if variation_num == 1:
        print("\n  Sample replacements:")
        for field_type, value in list(synthetic_data.items())[:5]:
            print(f"    {field_type}: {value}")

    # Apply replacements using DirectEditClient
    with DirectEditClient(pdf_path) as client:
        count = client.apply_template(template, synthetic_data)
        print(f"\n  Applied {count} replacements")
        result = client.save(output_path)
        print(f"  Saved: {result}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Test direct PDF editing pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_pdf", type=Path, help="Input PDF file")
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=None,
        help="Output directory (default: test_results/<filename>_direct)"
    )
    parser.add_argument(
        "-n", "--num-variations", type=int, default=1,
        help="Number of variations to generate (default: 1)"
    )
    parser.add_argument(
        "--template", type=Path, default=None,
        help="Use existing template file"
    )
    parser.add_argument(
        "--template-only", action="store_true",
        help="Create template only (no synthesis)"
    )
    parser.add_argument(
        "--save-template", type=Path, default=None,
        help="Save template to specified path"
    )

    args = parser.parse_args()

    if not args.input_pdf.exists():
        print(f"Error: File not found: {args.input_pdf}")
        sys.exit(1)

    # Setup
    setup_logging(log_level="INFO")
    settings = Settings()

    # Default output directory
    if args.output_dir is None:
        args.output_dir = Path("test_results") / f"{args.input_pdf.stem}_direct"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"DIRECT PDF EDITING PIPELINE: {args.input_pdf.name}")
    print(f"{'='*60}")
    print(f"Output: {args.output_dir}")

    # Check document type
    detector = DocumentDetector()
    doc_type = detector.detect(args.input_pdf)
    print(f"Document type: {doc_type}")

    if doc_type != "digital_pdf":
        print(f"\nWarning: This script is optimized for native PDFs.")
        print(f"For scanned documents, use full_pipeline.py instead.")
        if doc_type == "scanned_pdf":
            print("Proceeding anyway (OCR text may be less reliable)...")

    # Get or create template
    if args.template and args.template.exists():
        print(f"\nLoading template from: {args.template}")
        with open(args.template) as f:
            template = json.load(f)
    else:
        template = create_template_from_pdf(args.input_pdf, settings)

    # Save template if requested
    if args.save_template or args.template_only:
        template_path = args.save_template or (args.output_dir / "template.json")
        with open(template_path, "w") as f:
            json.dump(template, f, indent=2)
        print(f"\nTemplate saved: {template_path}")

    if args.template_only:
        print("\n--template-only flag set, skipping synthesis.")
        return

    # Generate variations
    results = []
    for i in range(args.num_variations):
        if args.num_variations > 1:
            output_path = args.output_dir / f"variation_{i+1:04d}.pdf"
        else:
            output_path = args.output_dir / f"{args.input_pdf.stem}_synthetic.pdf"

        result = generate_variation(
            args.input_pdf, template, output_path, settings, i + 1
        )
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("COMPLETE ✓")
    print(f"{'='*60}")
    print(f"\nGenerated {len(results)} PDF(s) in {args.output_dir}")
    for r in results:
        print(f"  - {r.name}")


if __name__ == "__main__":
    main()
