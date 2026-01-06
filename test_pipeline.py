#!/usr/bin/env python3
"""Testing script for Stirling PDF Synthetic Data Generator.

Usage:
    # Test single file
    python test_pipeline.py --file path/to/document.pdf

    # Test all files in a directory
    python test_pipeline.py --dir path/to/test_files/

    # Generate multiple variations
    python test_pipeline.py --file document.pdf --variations 5

    # Test with custom output directory
    python test_pipeline.py --dir test_files/ --output test_results/
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from stirling_sdg.config.settings import Settings
from stirling_sdg.pipeline.orchestrator import PipelineOrchestrator
from stirling_sdg.utils.logging_utils import get_logger

logger = get_logger(__name__)


class TestReport:
    """Tracks test results and generates summary reports."""

    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.start_time = time.time()

    def add_result(
        self,
        input_file: Path,
        success: bool,
        output_files: List[Path] = None,
        error: str = None,
        duration: float = 0,
        replacements_count: int = 0,
    ):
        """Add a test result."""
        self.results.append(
            {
                "input_file": str(input_file),
                "success": success,
                "output_files": [str(f) for f in (output_files or [])],
                "error": error,
                "duration": duration,
                "replacements_count": replacements_count,
            }
        )

    def print_summary(self):
        """Print test summary to console."""
        total_duration = time.time() - self.start_time
        successful = sum(1 for r in self.results if r["success"])
        failed = len(self.results) - successful

        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Total files tested: {len(self.results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Total duration: {total_duration:.2f}s")
        print()

        if successful > 0:
            print("SUCCESSFUL TESTS:")
            print("-" * 80)
            for result in self.results:
                if result["success"]:
                    print(f"  ✓ {Path(result['input_file']).name}")
                    print(f"    Replacements: {result['replacements_count']}")
                    print(f"    Duration: {result['duration']:.2f}s")
                    print(f"    Output files: {len(result['output_files'])}")
            print()

        if failed > 0:
            print("FAILED TESTS:")
            print("-" * 80)
            for result in self.results:
                if not result["success"]:
                    print(f"  ✗ {Path(result['input_file']).name}")
                    print(f"    Error: {result['error']}")
                    print(f"    Duration: {result['duration']:.2f}s")
            print()

    def save_json_report(self, output_path: Path):
        """Save detailed JSON report."""
        report = {
            "total_tests": len(self.results),
            "successful": sum(1 for r in self.results if r["success"]),
            "failed": sum(1 for r in self.results if not r["success"]),
            "total_duration": time.time() - self.start_time,
            "results": self.results,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nDetailed report saved to: {output_path}")


def get_test_files(path: Path, recursive: bool = False) -> List[Path]:
    """Get list of test files from path.

    Args:
        path: File or directory path
        recursive: Search recursively in subdirectories

    Returns:
        List of PDF and image files
    """
    if path.is_file():
        return [path]

    # Supported extensions
    extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}

    if recursive:
        files = []
        for ext in extensions:
            files.extend(path.rglob(f"*{ext}"))
        return sorted(files)
    else:
        files = []
        for ext in extensions:
            files.extend(path.glob(f"*{ext}"))
        return sorted(files)


def test_single_file(
    orchestrator: PipelineOrchestrator,
    input_file: Path,
    output_dir: Path,
    variations: int = 1,
    save_template: bool = True,
) -> Dict[str, Any]:
    """Test processing a single file.

    Args:
        orchestrator: Pipeline orchestrator
        input_file: Input file path
        output_dir: Output directory
        variations: Number of variations to generate
        save_template: Save classification template

    Returns:
        Test result dictionary
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"Testing: {input_file.name}")
    logger.info(f"{'='*80}")

    start_time = time.time()

    try:
        if variations == 1:
            # Single output
            output_path = output_dir / f"{input_file.stem}_synthetic{input_file.suffix}"
            result_path = orchestrator.process_single(
                input_file, output_path, save_template=save_template
            )
            output_files = [result_path]
            replacements_count = 0  # We'd need to read the template to get this

        else:
            # Multiple variations
            variation_dir = output_dir / input_file.stem
            output_files = orchestrator.process_batch(
                input_file, variation_dir, num_variations=variations
            )
            replacements_count = 0  # Same as above

        duration = time.time() - start_time

        logger.info(f"✓ Success! Generated {len(output_files)} file(s) in {duration:.2f}s")

        return {
            "success": True,
            "output_files": output_files,
            "duration": duration,
            "replacements_count": replacements_count,
        }

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"✗ Failed after {duration:.2f}s: {e}")
        return {
            "success": False,
            "output_files": [],
            "error": str(e),
            "duration": duration,
            "replacements_count": 0,
        }


def main():
    """Main testing function."""
    parser = argparse.ArgumentParser(
        description="Test Stirling PDF Synthetic Data Generator with various inputs"
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--file", type=Path, help="Single file to test")
    input_group.add_argument("--dir", type=Path, help="Directory of files to test")

    # Output options
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("test_results"),
        help="Output directory (default: test_results/)",
    )

    # Processing options
    parser.add_argument(
        "--variations",
        type=int,
        default=1,
        help="Number of variations to generate per file (default: 1)",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search directories recursively",
    )

    parser.add_argument(
        "--no-template",
        action="store_true",
        help="Don't save classification templates",
    )

    # Report options
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("test_results/test_report.json"),
        help="Path to save JSON test report",
    )

    args = parser.parse_args()

    # Get test files
    if args.file:
        test_files = [args.file]
    else:
        test_files = get_test_files(args.dir, recursive=args.recursive)

    if not test_files:
        print("No test files found!")
        return 1

    print(f"\nFound {len(test_files)} file(s) to test:")
    for f in test_files:
        print(f"  - {f.name}")
    print()

    # Initialize orchestrator
    settings = Settings()
    orchestrator = PipelineOrchestrator(settings)

    # Create test report
    report = TestReport()

    # Process each file
    for input_file in test_files:
        result = test_single_file(
            orchestrator=orchestrator,
            input_file=input_file,
            output_dir=args.output,
            variations=args.variations,
            save_template=not args.no_template,
        )

        report.add_result(
            input_file=input_file,
            success=result["success"],
            output_files=result["output_files"],
            error=result.get("error"),
            duration=result["duration"],
            replacements_count=result["replacements_count"],
        )

    # Print and save report
    report.print_summary()
    report.save_json_report(args.report)

    # Return exit code
    failed_count = sum(1 for r in report.results if not r["success"])
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
