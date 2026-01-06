"""Direct PDF editing client using PyMuPDF.

This module provides direct manipulation of native PDFs without full reconstruction.
It uses PyMuPDF (fitz) to search, redact, and replace text while preserving the
original document layout, fonts, and styling.

Use cases:
- Native/digital PDFs where layout preservation is critical
- Fast batch processing with template-based replacements
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # pymupdf

from ..utils.exceptions import StirlingAPIError
from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


class DirectEditClient:
    """Client for direct PDF editing using PyMuPDF.
    
    This client provides methods to:
    - Extract text with full style information (font, size, color, position)
    - Find and replace text with automatic style matching
    - Apply template-based bulk replacements for batch generation
    """

    def __init__(self, pdf_path: Optional[Path] = None):
        """Initialize DirectEditClient.

        Args:
            pdf_path: Optional path to PDF to open immediately
        """
        self.doc: Optional[fitz.Document] = None
        self.pdf_path: Optional[Path] = None
        
        if pdf_path:
            self.open(pdf_path)
        
        logger.info("DirectEditClient initialized")

    def open(self, pdf_path: Path) -> None:
        """Open a PDF for editing.

        Args:
            pdf_path: Path to PDF file

        Raises:
            StirlingAPIError: If file cannot be opened
        """
        try:
            self.pdf_path = Path(pdf_path)
            self.doc = fitz.open(str(self.pdf_path))
            logger.info(f"Opened PDF: {self.pdf_path.name} ({len(self.doc)} pages)")
        except Exception as e:
            logger.error(f"Failed to open PDF: {e}")
            raise StirlingAPIError(f"Failed to open PDF: {e}") from e

    def close(self) -> None:
        """Close the current document."""
        if self.doc:
            self.doc.close()
            self.doc = None
            self.pdf_path = None
            logger.debug("Document closed")

    def extract_text_elements(self) -> List[Dict[str, Any]]:
        """Extract all text elements with positions and styles.

        Returns:
            List of text elements with:
            - page: page number (0-indexed)
            - text: the text content
            - rect: bounding box [x0, y0, x1, y1]
            - font: font name
            - size: font size
            - color: RGB tuple (0-1 range)

        Raises:
            StirlingAPIError: If no document is open
        """
        if not self.doc:
            raise StirlingAPIError("No document open. Call open() first.")

        elements = []

        for page_num, page in enumerate(self.doc):
            # Get text as dictionary with full details
            text_dict = page.get_text("dict")

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:  # Type 0 = text block
                    continue

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue

                        # Extract color from integer
                        c_int = span.get("color", 0)
                        r = ((c_int >> 16) & 255) / 255
                        g = ((c_int >> 8) & 255) / 255
                        b = (c_int & 255) / 255

                        bbox = span.get("bbox", [0, 0, 0, 0])

                        element = {
                            "page": page_num,
                            "text": text,
                            "rect": list(bbox),
                            "font": span.get("font", "helv"),
                            "size": span.get("size", 12.0),
                            "color": (r, g, b),
                            "origin": span.get("origin", [bbox[0], bbox[3]]),
                        }
                        elements.append(element)

        logger.info(f"Extracted {len(elements)} text elements from {len(self.doc)} pages")
        return elements

    def find_text(self, search_text: str) -> List[Dict[str, Any]]:
        """Find all occurrences of text with style information.

        Args:
            search_text: Text to search for

        Returns:
            List of matches with page, rect, font, size, color

        Raises:
            StirlingAPIError: If no document is open
        """
        if not self.doc:
            raise StirlingAPIError("No document open. Call open() first.")

        matches = []

        for page_num, page in enumerate(self.doc):
            rects = page.search_for(search_text)

            for rect in rects:
                # Get style info from the found location
                text_dict = page.get_text("dict", clip=rect)

                # Default style
                font = "helv"
                size = 12.0
                color = (0.0, 0.0, 0.0)

                # Extract actual style from first matching span
                try:
                    for block in text_dict.get("blocks", []):
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                if span.get("text", "").strip():
                                    font = span.get("font", font)
                                    size = span.get("size", size)
                                    c_int = span.get("color", 0)
                                    r = ((c_int >> 16) & 255) / 255
                                    g = ((c_int >> 8) & 255) / 255
                                    b = (c_int & 255) / 255
                                    color = (r, g, b)
                                    break
                            else:
                                continue
                            break
                        else:
                            continue
                        break
                except Exception as e:
                    logger.warning(f"Could not extract style for '{search_text}': {e}")

                matches.append({
                    "page": page_num,
                    "text": search_text,
                    "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "font": font,
                    "size": size,
                    "color": color,
                })

        logger.info(f"Found {len(matches)} occurrences of '{search_text}'")
        return matches

    def find_and_replace(
        self,
        search_text: str,
        replace_text: str,
        match_style: bool = True
    ) -> int:
        """Find and replace text with optional style matching.

        Args:
            search_text: Text to find
            replace_text: Text to replace with
            match_style: If True, match original font size and color

        Returns:
            Number of replacements made

        Raises:
            StirlingAPIError: If no document is open
        """
        if not self.doc:
            raise StirlingAPIError("No document open. Call open() first.")

        replacements = 0

        for page_num, page in enumerate(self.doc):
            rects = page.search_for(search_text)

            if not rects:
                continue

            logger.debug(f"Page {page_num + 1}: Found {len(rects)} instance(s) of '{search_text}'")

            for rect in rects:
                # Get style info before redaction
                font_size = 12.0
                color = (0.0, 0.0, 0.0)

                if match_style:
                    text_dict = page.get_text("dict", clip=rect)
                    try:
                        for block in text_dict.get("blocks", []):
                            for line in block.get("lines", []):
                                for span in line.get("spans", []):
                                    if span.get("text", "").strip():
                                        font_size = span.get("size", font_size)
                                        c_int = span.get("color", 0)
                                        r = ((c_int >> 16) & 255) / 255
                                        g = ((c_int >> 8) & 255) / 255
                                        b = (c_int & 255) / 255
                                        color = (r, g, b)
                                        break
                                else:
                                    continue
                                break
                            else:
                                continue
                            break
                    except Exception as e:
                        logger.warning(f"Could not extract style: {e}")

                # Redact old text
                page.add_redact_annot(rect)
                page.apply_redactions()

                # Insert new text at bottom-left of rect (baseline position)
                page.insert_text(
                    point=rect.bl,
                    text=replace_text,
                    fontsize=font_size,
                    fontname="helv",
                    color=color,
                )

                replacements += 1

        logger.info(f"Replaced {replacements} occurrences of '{search_text}' with '{replace_text}'")
        return replacements

    def apply_template(
        self,
        template: Dict[str, Any],
        synthetic_data: Dict[str, Any]
    ) -> int:
        """Apply multiple replacements from a template.

        Args:
            template: Template with variable_fields list
            synthetic_data: Dict mapping field_type to replacement value (string or dict)

        Returns:
            Total number of replacements made

        Raises:
            StirlingAPIError: If no document is open
        """
        if not self.doc:
            raise StirlingAPIError("No document open. Call open() first.")

        variable_fields = template.get("variable_fields", [])
        total_replacements = 0

        for field in variable_fields:
            field_type = field.get("fieldType") or field.get("field_type")
            original_text = field.get("text") or field.get("original_text")

            if not field_type or not original_text:
                continue

            replacement = synthetic_data.get(field_type)
            if not replacement:
                logger.warning(f"No synthetic data for field type '{field_type}'")
                continue

            # Handle dict values (e.g., date ranges from LLM)
            if isinstance(replacement, dict):
                # Try to format as "start - end" for date ranges
                if "start_date" in replacement and "end_date" in replacement:
                    replacement = f"{replacement['start_date']} - {replacement['end_date']}"
                elif "start" in replacement and "end" in replacement:
                    replacement = f"{replacement['start']} - {replacement['end']}"
                else:
                    # Fallback: join all values
                    replacement = " ".join(str(v) for v in replacement.values())
            elif not isinstance(replacement, str):
                replacement = str(replacement)

            count = self.find_and_replace(original_text, replacement)
            total_replacements += count

        logger.info(f"Applied template: {total_replacements} total replacements")
        return total_replacements

    def save(self, output_path: Optional[Path] = None) -> Path:
        """Save the modified PDF.

        Args:
            output_path: Path to save to (defaults to new file next to original)

        Returns:
            Path to saved file

        Raises:
            StirlingAPIError: If no document is open or save fails
        """
        if not self.doc:
            raise StirlingAPIError("No document open. Call open() first.")

        if output_path is None:
            if self.pdf_path:
                output_path = self.pdf_path.parent / f"{self.pdf_path.stem}_edited.pdf"
            else:
                output_path = Path("output.pdf")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.doc.save(str(output_path))
            logger.info(f"Saved modified PDF to: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to save PDF: {e}")
            raise StirlingAPIError(f"Failed to save PDF: {e}") from e

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close document."""
        self.close()
        return False
