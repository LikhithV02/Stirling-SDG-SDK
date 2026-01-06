#!/usr/bin/env python3
"""Test PDF extraction and reconstruction only (no synthesis).

Usage:
    python test_extraction.py <input_file> [--output-dir <dir>] [--force-ocr]
    python test_extraction.py <input_file> --resolve-collisions --add-word-spacing

Arguments:
    input_file      Path to input PDF or image file
    --output-dir    Output directory for results (default: test_results/<filename>_extraction)
    --force-ocr     Force OCR even for native PDFs
    --resolve-collisions  Enable collision resolution for text elements
    --add-word-spacing    Enable word spacing between adjacent text elements
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.stirling_sdg.config.settings import Settings
from src.stirling_sdg.stirling.client import StirlingClient
from src.stirling_sdg.detection.detector import DocumentDetector
from src.stirling_sdg.utils.logging_utils import setup_logging


def run_extraction_test(
    input_path: Path,
    output_dir: Path,
    force_ocr: bool = False,
    resolve_collisions: bool = False,
    add_word_spacing: bool = False,
):
    """Run PDF extraction and reconstruction test.

    Outputs:
        1. extracted.json - Original PDF extracted to JSON
        2. reconstructed.pdf - PDF reconstructed from extracted JSON
    """
    # Setup
    setup_logging(log_level="INFO")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize components
    detector = DocumentDetector()
    stirling = StirlingClient(cache_dir=output_dir)
    
    print(f"\n{'='*70}")
    print(f"PDF EXTRACTION & RECONSTRUCTION TEST: {input_path.name}")
    print(f"{'='*70}")
    print(f"Output directory: {output_dir}")
    print(f"Options: resolve_collisions={resolve_collisions}, add_word_spacing={add_word_spacing}")
    print()

    # Step 0: Detect document type and prepare searchable PDF
    print("Step 0: Document Detection & Preparation")
    print("-" * 70)
    doc_type = detector.detect(input_path)
    print(f"  Document type: {doc_type}")

    searchable_pdf = input_path
    if doc_type == "image":
        print("  Converting image to PDF...")
        pdf_path = stirling.convert_image_to_pdf(input_path)
        print("  Applying OCR...")
        searchable_pdf = stirling.ocr_pdf(pdf_path, languages=["eng"], ocr_type="force-ocr")
        print(f"  ✓ Searchable PDF: {searchable_pdf.name}")
    elif doc_type == "scanned_pdf" or force_ocr:
        print("  Applying OCR to scanned PDF...")
        searchable_pdf = stirling.ocr_pdf(input_path, languages=["eng"], ocr_type="force-ocr")
        print(f"  ✓ Searchable PDF: {searchable_pdf.name}")
    else:
        print("  ✓ Document is already searchable")

    # Step 1: PDF → JSON Extraction
    print(f"\n{'='*70}")
    print("Step 1: PDF → JSON Extraction")
    print("-" * 70)
    try:
        pdf_json = stirling.pdf_to_json(searchable_pdf)
        pages = pdf_json.get("pages", [])
        total_text = sum(len(p.get("textElements", [])) for p in pages)
        total_lines = sum(len(p.get("lineElements", [])) for p in pages)
        total_rects = sum(len(p.get("rectElements", [])) for p in pages)
        total_curves = sum(len(p.get("curveElements", [])) for p in pages)
        
        print(f"  ✓ Extracted PDF to JSON")
        print(f"  Pages: {len(pages)}")
        print(f"  Text elements: {total_text}")
        print(f"  Lines: {total_lines}, Rectangles: {total_rects}, Curves: {total_curves}")

        # Save extracted JSON
        extracted_json_path = output_dir / "extracted.json"
        with open(extracted_json_path, "w") as f:
            json.dump(pdf_json, f, indent=2)
        print(f"  Saved: {extracted_json_path.name}")

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        raise

    # Step 2: Reconstruct PDF from extracted JSON
    print(f"\n{'='*70}")
    print("Step 2: Reconstruct PDF from Extracted JSON")
    print("-" * 70)
    try:
        reconstructed_path = output_dir / "reconstructed.pdf"
        stirling.json_to_pdf(
            pdf_json, 
            reconstructed_path,
            resolve_collisions=resolve_collisions,
            add_word_spacing=add_word_spacing
        )
        print(f"  ✓ Reconstructed PDF")
        print(f"  Saved: {reconstructed_path.name}")
        print(f"  Size: {reconstructed_path.stat().st_size / 1024:.1f} KB")

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        raise

    # Summary
    print(f"\n{'='*70}")
    print("EXTRACTION TEST COMPLETE ✓")
    print(f"{'='*70}")
    print(f"\nOutput files in {output_dir}:")
    print(f"  - extracted.json - Original PDF content as JSON")
    print(f"  - reconstructed.pdf - PDF rebuilt from JSON")
    print()

    return {
        "extracted_json": extracted_json_path,
        "reconstructed_pdf": reconstructed_path,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Test PDF extraction and reconstruction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_extraction.py scan.pdf
  python test_extraction.py image.png --output-dir ./results
  python test_extraction.py native.pdf --force-ocr
  python test_extraction.py form.pdf --resolve-collisions
  python test_extraction.py form.pdf --resolve-collisions --add-word-spacing
        """
    )
    parser.add_argument("input_file", type=Path, help="Input PDF or image file")
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=None,
        help="Output directory (default: test_results/<filename>_extraction)"
    )
    parser.add_argument(
        "--force-ocr", action="store_true",
        help="Force OCR even for native PDFs"
    )
    parser.add_argument(
        "--resolve-collisions", action="store_true",
        help="Enable collision resolution for overlapping text"
    )
    parser.add_argument(
        "--add-word-spacing", action="store_true",
        help="Enable minimum word spacing between adjacent text"
    )

    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"Error: File not found: {args.input_file}")
        sys.exit(1)

    # Default output directory
    if args.output_dir is None:
        args.output_dir = Path("test_results") / f"{args.input_file.stem}_extraction"

    try:
        results = run_extraction_test(
            input_path=args.input_file,
            output_dir=args.output_dir,
            force_ocr=args.force_ocr,
            resolve_collisions=args.resolve_collisions,
            add_word_spacing=args.add_word_spacing,
        )
        print("All outputs generated successfully!")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
