#!/usr/bin/env python3
"""End-to-end test for the complete workflow.

Usage:
    python test_end_to_end.py <input_file> [--output-dir <dir>] [--skip-synthesis]

Arguments:
    input_file      Path to input PDF or image file
    --output-dir    Output directory for results (default: test_results/<filename>)
    --skip-synthesis Skip LLM-based synthesis step (for faster testing)
    --force-ocr     Force OCR even for native PDFs
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
from src.stirling_sdg.classification.classifier import ContentClassifier
from src.stirling_sdg.synthesis.generator import SyntheticDataGenerator
from src.stirling_sdg.json_editor.editor import JSONEditor
from src.stirling_sdg.utils.logging_utils import setup_logging


def run_end_to_end(
    input_path: Path,
    output_dir: Path,
    skip_synthesis: bool = False,
    force_ocr: bool = False,
    num_variations: int = 1,
):
    """Run end-to-end workflow on a document.

    Outputs:
        1. extracted.json - Original PDF extracted to JSON
        2. reconstructed_original.pdf - PDF reconstructed from extracted JSON
        3. template.json - Classification template
        4. synthesis_NNN.json - JSON with synthetic data (N variations)
        5. synthesis_NNN.pdf - PDF with synthetic data (N variations)
    """
    # Setup
    setup_logging(log_level="INFO")
    settings = Settings()
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize components
    detector = DocumentDetector()
    stirling = StirlingClient(cache_dir=output_dir)
    
    print(f"\n{'='*70}")
    print(f"END-TO-END WORKFLOW: {input_path.name}")
    print(f"{'='*70}")
    print(f"Output directory: {output_dir}")
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

    # Step 1: PDF → JSON
    print(f"\n{'='*70}")
    print("Step 1: PDF → JSON Extraction")
    print("-" * 70)
    try:
        pdf_json = stirling.pdf_to_json(searchable_pdf)
        total_elements = sum(len(p.get("textElements", [])) for p in pdf_json.get("pages", []))
        print(f"  ✓ Extracted PDF to JSON")
        print(f"  Pages: {len(pdf_json.get('pages', []))}")
        print(f"  Text elements: {total_elements}")

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
        reconstructed_original = output_dir / "reconstructed_original.pdf"
        stirling.json_to_pdf(pdf_json, reconstructed_original)
        print(f"  ✓ Reconstructed PDF")
        print(f"  Saved: {reconstructed_original.name}")
        print(f"  Size: {reconstructed_original.stat().st_size / 1024:.1f} KB")

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        raise

    if skip_synthesis:
        print(f"\n{'='*70}")
        print("SKIPPING SYNTHESIS (--skip-synthesis flag)")
        print(f"{'='*70}\n")
        return {
            "extracted_json": extracted_json_path,
            "reconstructed_original": reconstructed_original,
        }

    # Step 3: Classify variable fields
    print(f"\n{'='*70}")
    print("Step 3: Classify Variable Fields (LLM)")
    print("-" * 70)
    try:
        classifier = ContentClassifier(settings)
        template = classifier.classify(pdf_json)
        variable_fields = template.get("variable_fields", [])
        print(f"  ✓ Classification complete")
        print(f"  Variable fields: {len(variable_fields)}")

        # Save classification template
        template_path = output_dir / "template.json"
        with open(template_path, "w") as f:
            json.dump(template, f, indent=2)
        print(f"  Saved: {template_path.name}")

        if variable_fields:
            print(f"\n  Sample fields:")
            for elem in variable_fields[:5]:
                print(f"    - '{elem.get('text', '')[:30]}' → {elem.get('fieldType')}")

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        raise

    # Steps 4-6: Generate N variations
    generator = SyntheticDataGenerator(settings)
    json_editor = JSONEditor()
    
    synthesis_outputs = []
    
    for variation in range(1, num_variations + 1):
        var_suffix = f"_{variation:03d}" if num_variations > 1 else ""
        
        # Step 4: Generate synthetic data
        print(f"\n{'='*70}")
        print(f"Step 4: Generate Synthetic Data (LLM){f' - Variation {variation}/{num_variations}' if num_variations > 1 else ''}")
        print("-" * 70)
        try:
            synthetic_data = generator.generate(template)
            print(f"  ✓ Synthetic data generated")
            print(f"  Fields: {len(synthetic_data)}")

            if synthetic_data and variation == 1:
                print(f"\n  Sample values:")
                for field_type, value in list(synthetic_data.items())[:5]:
                    print(f"    {field_type}: {value}")

        except Exception as e:
            print(f"  ✗ Failed: {e}")
            raise

        # Step 5: Replace text in JSON
        print(f"\n{'='*70}")
        print(f"Step 5: Replace Text in JSON (Synthesis){f' - Variation {variation}/{num_variations}' if num_variations > 1 else ''}")
        print("-" * 70)
        try:
            modified_json = json_editor.replace_text(pdf_json, template, synthetic_data)
            print(f"  ✓ Text replacement complete")

            # Save synthesis JSON
            synthesis_json_path = output_dir / f"synthesis{var_suffix}.json"
            with open(synthesis_json_path, "w") as f:
                json.dump(modified_json, f, indent=2)
            print(f"  Saved: {synthesis_json_path.name}")

        except Exception as e:
            print(f"  ✗ Failed: {e}")
            raise

        # Step 6: Reconstruct PDF from synthesis JSON
        print(f"\n{'='*70}")
        print(f"Step 6: Reconstruct PDF from Synthesis JSON{f' - Variation {variation}/{num_variations}' if num_variations > 1 else ''}")
        print("-" * 70)
        try:
            reconstructed_synthesis = output_dir / f"synthesis{var_suffix}.pdf"
            stirling.json_to_pdf(modified_json, reconstructed_synthesis)
            print(f"  ✓ Reconstructed synthesis PDF")
            print(f"  Saved: {reconstructed_synthesis.name}")
            print(f"  Size: {reconstructed_synthesis.stat().st_size / 1024:.1f} KB")
            
            synthesis_outputs.append({
                "json": synthesis_json_path,
                "pdf": reconstructed_synthesis,
            })

        except Exception as e:
            print(f"  ✗ Failed: {e}")
            raise

    # Summary
    print(f"\n{'='*70}")
    print("WORKFLOW COMPLETE ✓")
    print(f"{'='*70}")
    print(f"\nOutput files in {output_dir}:")
    print(f"  - extracted.json - Original PDF content")
    print(f"  - reconstructed_original.pdf - PDF from original JSON")
    print(f"  - template.json - Classification template")
    if num_variations == 1:
        print(f"  - synthesis.json - JSON with synthetic data")
        print(f"  - synthesis.pdf - PDF with synthetic data")
    else:
        print(f"  - synthesis_001.json ... synthesis_{num_variations:03d}.json")
        print(f"  - synthesis_001.pdf ... synthesis_{num_variations:03d}.pdf")
    print()

    return {
        "extracted_json": extracted_json_path,
        "reconstructed_original": reconstructed_original,
        "template": template_path,
        "synthesis_outputs": synthesis_outputs,
    }


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end test for PDF synthetic data generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_end_to_end.py scan.pdf
  python test_end_to_end.py image.png --output-dir ./results
  python test_end_to_end.py form.pdf --skip-synthesis
  python test_end_to_end.py native.pdf --force-ocr
  python test_end_to_end.py form.pdf -n 10  # Generate 10 variations
        """
    )
    parser.add_argument("input_file", type=Path, help="Input PDF or image file")
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=None,
        help="Output directory (default: test_results/<filename>)"
    )
    parser.add_argument(
        "--num-variations", "-n", type=int, default=1,
        help="Number of synthetic variations to generate (default: 1)"
    )
    parser.add_argument(
        "--skip-synthesis", action="store_true",
        help="Skip LLM-based synthesis step"
    )
    parser.add_argument(
        "--force-ocr", action="store_true",
        help="Force OCR even for native PDFs"
    )

    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"Error: File not found: {args.input_file}")
        sys.exit(1)

    # Default output directory
    if args.output_dir is None:
        args.output_dir = Path("test_results") / args.input_file.stem

    try:
        results = run_end_to_end(
            input_path=args.input_file,
            output_dir=args.output_dir,
            skip_synthesis=args.skip_synthesis,
            force_ocr=args.force_ocr,
            num_variations=args.num_variations,
        )
        print("All outputs generated successfully!")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
