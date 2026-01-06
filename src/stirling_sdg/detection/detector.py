"""Document type detector."""

from pathlib import Path
from typing import Literal

from ..utils.logging_utils import get_logger

logger = get_logger(__name__)

DocumentType = Literal["image", "scanned_pdf", "digital_pdf"]


class DocumentDetector:
    """Detects whether input is an image, scanned PDF, or digital PDF."""

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}

    def detect(self, file_path: Path) -> DocumentType:
        """Detect document type.

        Args:
            file_path: Path to input file

        Returns:
            Document type: 'image', 'scanned_pdf', or 'digital_pdf'
        """
        logger.info(f"Starting document detection for: {file_path.name}")

        # Check if it's an image
        if file_path.suffix.lower() in self.IMAGE_EXTENSIONS:
            logger.info(f"Detected image file: {file_path.name}")
            return "image"

        # If it's a PDF, check if it's digital or scanned
        if file_path.suffix.lower() == ".pdf":
            logger.info(f"Analyzing PDF to determine if digital or scanned: {file_path.name}")
            is_digital = self._is_digital_pdf(file_path)
            doc_type = "digital_pdf" if is_digital else "scanned_pdf"
            logger.info(f"Detected {doc_type}: {file_path.name}")
            return doc_type

        # Unknown file type
        logger.warning(f"Unknown file type: {file_path.suffix}")
        return "scanned_pdf"  # Default to scanned for safety

    def _is_digital_pdf(self, pdf_path: Path) -> bool:
        """Check if PDF is digital (has extractable text) or scanned.

        Args:
            pdf_path: Path to PDF file

        Returns:
            True if digital PDF, False if scanned
        """
        try:
            # Try to use PyMuPDF if available (fast and reliable)
            try:
                import fitz

                logger.debug("Using PyMuPDF (fitz) for PDF analysis")
                doc = fitz.open(pdf_path)

                # Check first page only for efficiency
                if len(doc) == 0:
                    logger.warning(f"PDF has no pages: {pdf_path.name}")
                    doc.close()
                    return False

                logger.debug(f"Analyzing first page of {len(doc)}-page PDF")
                first_page = doc[0]

                # Extract text
                text = first_page.get_text().strip()
                total_text_length = len(text)

                # Check for embedded fonts
                has_fonts = len(first_page.get_fonts()) > 0

                # Calculate text coverage (rough estimate)
                page_area = first_page.rect.width * first_page.rect.height
                # Assume average character takes ~20 square units
                estimated_text_area = total_text_length * 20
                text_coverage = min(
                    100, (estimated_text_area / page_area * 100) if page_area > 0 else 0
                )

                doc.close()

                # Decision criteria
                # Relaxed criteria: 
                # 1. Has embedded fonts and meaningful text length (> 100 chars)
                # 2. OR has substantial text (> 500 chars) even if font detection is ambiguous
                is_digital = (has_fonts and total_text_length > 100) or (total_text_length > 500)

                logger.info(
                    f"PDF analysis: text_coverage={text_coverage:.1f}%, "
                    f"has_fonts={has_fonts}, text_length={total_text_length}, "
                    f"is_digital={is_digital}"
                )

                return is_digital

            except ImportError:
                # PyMuPDF not available, try pdfplumber
                logger.debug("PyMuPDF not available, trying pdfplumber")
                try:
                    import pdfplumber

                    logger.debug("Using pdfplumber for PDF analysis")
                    with pdfplumber.open(pdf_path) as pdf:
                        if len(pdf.pages) == 0:
                            logger.warning(f"PDF has no pages: {pdf_path.name}")
                            return False

                        logger.debug(f"Analyzing first page of {len(pdf.pages)}-page PDF")
                        first_page = pdf.pages[0]
                        text = first_page.extract_text()

                        if text:
                            text_length = len(text.strip())
                            is_digital = text_length > 200
                            logger.info(
                                f"PDF analysis (pdfplumber): text_length={text_length}, "
                                f"is_digital={is_digital}"
                            )
                            # Simple heuristic: if we extracted substantial text, it's digital
                            return is_digital
                        logger.info("No extractable text found, treating as scanned PDF")
                        return False

                except ImportError:
                    # Neither library available, default to scanned
                    logger.warning(
                        "Neither PyMuPDF nor pdfplumber available for PDF analysis. "
                        "Defaulting to scanned_pdf. Install with: pip install pymupdf"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error analyzing PDF: {e}")
            return False  # Default to scanned on error
