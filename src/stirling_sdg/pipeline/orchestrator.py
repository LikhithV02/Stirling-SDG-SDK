"""Pipeline orchestrator for coordinating the complete workflow."""

from pathlib import Path
from typing import List

from ..config.settings import Settings
from ..stirling.client import StirlingClient
from ..stirling.direct_edit_client import DirectEditClient
from ..detection.detector import DocumentDetector
from ..classification.classifier import ContentClassifier
from ..synthesis.generator import SyntheticDataGenerator
from ..json_editor.editor import JSONEditor
from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


class PipelineOrchestrator:
    """Orchestrates the end-to-end synthetic data generation workflow."""

    def __init__(self, settings: Settings | None = None):
        """Initialize orchestrator with all components.

        Args:
            settings: Application settings (loads from env if not provided)
        """
        if settings is None:
            settings = Settings()

        self.settings = settings

        # Initialize all components
        self.detector = DocumentDetector()
        self.stirling = StirlingClient(cache_dir=settings.cache_dir)
        self.classifier = ContentClassifier(settings)
        self.generator = SyntheticDataGenerator(settings)
        self.json_editor = JSONEditor()

        logger.info("PipelineOrchestrator initialized")

    def process_single(
        self, input_path: Path, output_path: Path, save_template: bool = False
    ) -> Path:
        """Process a single document through the complete pipeline.

        Args:
            input_path: Path to input PDF or image
            output_path: Path for output PDF
            save_template: If True, save classification template for reuse

        Returns:
            Path to generated PDF

        Workflow:
            For native PDFs (digital_pdf):
                1. Use DirectEditClient for fast, layout-preserving edits
            For scanned PDFs/images:
                1. Convert to searchable PDF if needed (OCR)
                2. Extract PDF to JSON
                3. Classify variable vs static fields
                4. Generate synthetic data
                5. Replace text in JSON
                6. Reconstruct PDF from JSON
        """
        # Ensure output path has .pdf extension
        if output_path.suffix.lower() != ".pdf":
            logger.warning(
                f"Output path has extension '{output_path.suffix}' but output is always a PDF. "
                f"Changing to .pdf extension."
            )
            output_path = output_path.with_suffix(".pdf")

        logger.info(f"Processing single document: {input_path.name}")
        logger.info(f"Output will be saved to: {output_path}")

        # Step 1: Detect document type
        doc_type = self.detector.detect(input_path)
        logger.info(f"Document type: {doc_type}")

        # Route based on document type
        if doc_type == "digital_pdf":
            # Use direct editing path for native PDFs (faster, preserves layout)
            return self._process_native_pdf(input_path, output_path, save_template)
        else:
            # Use OCR + reconstruction path for scanned/images
            return self._process_scanned_pdf(input_path, output_path, doc_type, save_template)

    def _process_native_pdf(
        self, input_path: Path, output_path: Path, save_template: bool = False
    ) -> Path:
        """Process native PDF using direct editing (fast, preserves layout).

        Args:
            input_path: Path to native PDF
            output_path: Path for output PDF
            save_template: If True, save template for reuse

        Returns:
            Path to generated PDF
        """
        logger.info("Using direct editing path for native PDF")

        # Step 1: Extract text elements with styles
        with DirectEditClient(input_path) as client:
            text_elements = client.extract_text_elements()

            # Build a pseudo-JSON for classification
            # Group elements by page
            pages_data = {}
            for elem in text_elements:
                page_num = elem["page"] + 1  # 1-indexed for classifier
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

            # Step 2: Classify variable fields
            logger.info("Classifying variable fields...")
            template = self.classifier.classify(pdf_json)

            # Enrich template with direct-edit metadata
            template["type"] = "direct_edit"
            template["source_file"] = str(input_path)

            # Add positional info from extracted elements for direct replacement
            for field in template.get("variable_fields", []):
                field_text = field.get("text", "")
                # Find matching element to get exact position and style
                for elem in text_elements:
                    if elem["text"] == field_text:
                        field["rect"] = elem["rect"]
                        field["font"] = elem["font"]
                        field["size"] = elem["size"]
                        field["color"] = elem["color"]
                        field["page"] = elem["page"]
                        break

            # Save template if requested
            if save_template:
                template_path = (
                    self.settings.config_dir
                    / "templates"
                    / f"{input_path.stem}_template.json"
                )
                self._save_template(template, template_path)
                logger.info(f"Template saved to: {template_path}")

            # Step 3: Generate synthetic data
            logger.info("Generating synthetic data...")
            synthetic_data = self.generator.generate(template)

            # Step 4: Apply replacements directly
            logger.info("Applying direct replacements...")
            count = client.apply_template(template, synthetic_data)
            logger.info(f"Made {count} replacements")

            # Step 5: Save output
            result = client.save(output_path)
            logger.info(f"Successfully generated: {result}")
            return result

    def _process_scanned_pdf(
        self, input_path: Path, output_path: Path, doc_type: str, save_template: bool = False
    ) -> Path:
        """Process scanned PDF/image using OCR + JSON reconstruction.

        Args:
            input_path: Path to scanned PDF or image
            output_path: Path for output PDF
            doc_type: Document type from detector
            save_template: If True, save template for reuse

        Returns:
            Path to generated PDF
        """
        logger.info("Using OCR + reconstruction path for scanned document")

        # Step 1: Ensure searchable PDF
        searchable_pdf = self._ensure_searchable(input_path, doc_type)

        # Step 2: PDF → JSON
        logger.info("Extracting PDF to JSON...")
        pdf_json = self.stirling.pdf_to_json(searchable_pdf)

        # Step 3: Classify variable fields
        logger.info("Classifying variable fields...")
        template = self.classifier.classify(pdf_json)
        template["type"] = "reconstruction"

        # Save template if requested
        if save_template:
            template_path = (
                self.settings.config_dir
                / "templates"
                / f"{input_path.stem}_template.json"
            )
            self._save_template(template, template_path)
            logger.info(f"Template saved to: {template_path}")

        # Step 4: Generate synthetic data
        logger.info("Generating synthetic data...")
        synthetic_data = self.generator.generate(template)

        # Step 5: Replace text in JSON
        logger.info("Replacing text in JSON...")
        modified_json = self.json_editor.replace_text(
            pdf_json, template, synthetic_data
        )

        # Step 6: JSON → PDF
        logger.info("Reconstructing PDF from JSON...")
        try:
            result = self.stirling.json_to_pdf(modified_json, output_path)
            logger.info(f"Successfully generated: {result}")
            return result
        except Exception as e:
            logger.error(f"PDF reconstruction failed: {e}")
            # Save modified JSON for debugging
            fallback_path = output_path.with_suffix(".json")
            import json

            with open(fallback_path, "w") as f:
                json.dump(modified_json, f, indent=2)
            logger.info(f"Modified JSON saved to: {fallback_path}")
            raise

    def process_batch(
        self,
        input_path: Path,
        output_dir: Path,
        num_variations: int = 10,
        template_path: Path | None = None,
    ) -> List[Path]:
        """Generate multiple variations with template reuse for efficiency.

        Args:
            input_path: Path to input PDF or image
            output_dir: Directory for output PDFs
            num_variations: Number of variations to generate
            template_path: Optional pre-saved template (skips classification)

        Returns:
            List of paths to generated PDFs

        Efficiency:
            - Detects and classifies ONCE
            - Generates N different synthetic datasets
            - Creates N output PDFs using appropriate method
            - Native PDFs use direct editing (fast)
            - Scanned PDFs use JSON reconstruction
        """
        logger.info(
            f"Starting batch processing: {num_variations} variations of {input_path.name}"
        )

        output_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1: Template extraction (do ONCE)
        doc_type = self.detector.detect(input_path)
        
        if template_path and template_path.exists():
            logger.info(f"Loading template from: {template_path}")
            template = self._load_template(template_path)
        else:
            logger.info("Extracting template from input document...")
            
            if doc_type == "digital_pdf":
                # Extract template using direct edit method
                with DirectEditClient(input_path) as client:
                    text_elements = client.extract_text_elements()
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
                    template = self.classifier.classify(pdf_json)
                    template["type"] = "direct_edit"
                    template["source_file"] = str(input_path)
                    
                    # Enrich with positional info
                    for field in template.get("variable_fields", []):
                        field_text = field.get("text", "")
                        for elem in text_elements:
                            if elem["text"] == field_text:
                                field["rect"] = elem["rect"]
                                field["font"] = elem["font"]
                                field["size"] = elem["size"]
                                field["color"] = elem["color"]
                                field["page"] = elem["page"]
                                break
            else:
                # Extract template using OCR/reconstruction method
                searchable_pdf = self._ensure_searchable(input_path, doc_type)
                pdf_json = self.stirling.pdf_to_json(searchable_pdf)
                template = self.classifier.classify(pdf_json)
                template["type"] = "reconstruction"

            # Save template for future use
            auto_template_path = (
                self.settings.config_dir
                / "templates"
                / f"{input_path.stem}_template.json"
            )
            self._save_template(template, auto_template_path)
            logger.info(f"Template saved to: {auto_template_path}")

        # Phase 2: Generate N variations
        logger.info(
            f"Template ready (type: {template.get('type', 'unknown')}). Generating {num_variations} variations..."
        )
        results = []
        
        # Determine processing method based on template type
        is_direct_edit = template.get("type") == "direct_edit"
        
        if not is_direct_edit:
            # Need pdf_json for reconstruction path
            if doc_type == "digital_pdf":
                pdf_json = self.stirling.pdf_to_json(input_path)
            else:
                searchable_pdf = self._ensure_searchable(input_path, doc_type)
                pdf_json = self.stirling.pdf_to_json(searchable_pdf)

        for i in range(num_variations):
            try:
                # Generate unique synthetic data
                synthetic_data = self.generator.generate(template)

                output_path = output_dir / f"variation_{i + 1:04d}.pdf"
                
                if is_direct_edit:
                    # Use direct editing for native PDFs
                    with DirectEditClient(input_path) as client:
                        client.apply_template(template, synthetic_data)
                        client.save(output_path)
                    results.append(output_path)
                else:
                    # Use JSON reconstruction for scanned PDFs
                    modified_json = self.json_editor.replace_text(
                        pdf_json, template, synthetic_data
                    )
                    result = self.stirling.json_to_pdf(modified_json, output_path)
                    results.append(result)

                if (i + 1) % 10 == 0 or (i + 1) == num_variations:
                    logger.info(f"Progress: {i + 1}/{num_variations} variations generated")

            except Exception as e:
                logger.error(f"Failed to generate variation {i + 1}: {e}")
                continue

        logger.info(
            f"Batch processing complete: {len(results)}/{num_variations} successful"
        )
        return results

    def _ensure_searchable(self, input_path: Path, doc_type: str) -> Path:
        """Convert to searchable PDF if needed.

        Args:
            input_path: Path to input file
            doc_type: Document type from detector

        Returns:
            Path to searchable PDF
        """
        if doc_type == "digital_pdf":
            logger.info("Document is already a digital PDF (searchable)")
            return input_path

        elif doc_type == "image":
            logger.info("Converting image to PDF...")
            pdf_path = self.stirling.convert_image_to_pdf(input_path)
            logger.info("Applying OCR to converted PDF...")
            return self.stirling.ocr_pdf(
                pdf_path, languages=self.settings.ocr_languages_list
            )

        elif doc_type == "scanned_pdf":
            logger.info("Applying OCR to scanned PDF...")
            return self.stirling.ocr_pdf(
                input_path, languages=self.settings.ocr_languages_list
            )

        else:
            # Unknown type, try OCR anyway
            logger.warning(f"Unknown document type: {doc_type}, attempting OCR")
            return self.stirling.ocr_pdf(
                input_path, languages=self.settings.ocr_languages_list
            )

    def _save_template(self, template: dict, template_path: Path):
        """Save classification template to file.

        Args:
            template: Classification result
            template_path: Path to save template
        """
        import json

        template_path.parent.mkdir(parents=True, exist_ok=True)
        with open(template_path, "w") as f:
            json.dump(template, f, indent=2)

    def _load_template(self, template_path: Path) -> dict:
        """Load classification template from file.

        Args:
            template_path: Path to template file

        Returns:
            Classification template
        """
        import json

        with open(template_path, "r") as f:
            return json.load(f)
