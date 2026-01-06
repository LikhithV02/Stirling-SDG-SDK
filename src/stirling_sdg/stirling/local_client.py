"""Local PDF processing client - replaces Stirling PDF Docker dependency.

This module implements the same interface as StirlingClient but uses local
Python libraries instead of making HTTP calls to a Stirling PDF Docker container.

Libraries used:
- pdfplumber: PDF text/layout extraction
- reportlab: PDF generation from JSON
- ocrmypdf: OCR for scanned PDFs (requires tesseract)
- img2pdf: Image to PDF conversion
- PIL: Image handling
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

import img2pdf
import pdfplumber
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from ..utils.exceptions import StirlingAPIError
from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


class LocalStirlingClient:
    """Local client for PDF processing - replaces Stirling PDF Docker.
    
    This client implements the same interface as StirlingClient but uses
    local Python libraries instead of HTTP calls to a Docker container.
    """

    def __init__(self, cache_dir: Path | None = None):
        """Initialize local PDF client.

        Args:
            cache_dir: Directory for temporary/cached files
        """
        if cache_dir is None:
            from ..config.settings import Settings
            settings = Settings()
            self.cache_dir = settings.cache_dir
        else:
            self.cache_dir = cache_dir
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._check_dependencies()
        logger.info("LocalStirlingClient initialized (no Docker required)")

    def _check_dependencies(self):
        """Check if required external dependencies are available."""
        # Check for tesseract (required by ocrmypdf)
        try:
            result = subprocess.run(
                ["tesseract", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                logger.info(f"Tesseract found: {version_line}")
            else:
                logger.warning("Tesseract check returned non-zero, OCR may not work")
        except FileNotFoundError:
            logger.warning(
                "Tesseract not found. OCR will not work. "
                "Install with: brew install tesseract (macOS) or apt-get install tesseract-ocr (Linux)"
            )
        except Exception as e:
            logger.warning(f"Could not verify tesseract installation: {e}")

    def ocr_pdf(
        self,
        input_path: Path,
        languages: list[str] | None = None,
        ocr_type: str = "skip-text",
    ) -> Path:
        """Apply OCR to PDF using ocrmypdf.

        Args:
            input_path: Path to input PDF
            languages: List of OCR languages (default: ["eng"])
            ocr_type: "skip-text" or "force-ocr"

        Returns:
            Path to OCR'd PDF (saved in cache)

        Raises:
            StirlingAPIError: If OCR fails
        """
        if languages is None:
            languages = ["eng"]

        file_size = input_path.stat().st_size
        lang_str = "+".join(languages)
        logger.info(
            f"Applying OCR to {input_path.name} ({file_size / 1024:.1f} KB, languages: {lang_str})"
        )

        output_path = self.cache_dir / f"ocr_{input_path.stem}.pdf"

        try:
            import ocrmypdf

            # Map ocr_type to ocrmypdf options
            skip_text = ocr_type == "skip-text"
            force_ocr = ocr_type == "force-ocr"

            ocrmypdf.ocr(
                input_path,
                output_path,
                language=lang_str,
                skip_text=skip_text,
                force_ocr=force_ocr,
                deskew=True,
                optimize=1,
                progress_bar=False,
            )

            logger.info(f"OCR completed: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"OCR failed: {e}")
            raise StirlingAPIError(f"OCR failed: {e}") from e

    def convert_image_to_pdf(self, image_path: Path) -> Path:
        """Convert image to PDF using img2pdf.

        Args:
            image_path: Path to input image

        Returns:
            Path to converted PDF (saved in cache)

        Raises:
            StirlingAPIError: If conversion fails
        """
        file_size = image_path.stat().st_size
        logger.info(f"Converting image to PDF: {image_path.name} ({file_size / 1024:.1f} KB)")

        output_path = self.cache_dir / f"converted_{image_path.stem}.pdf"

        try:
            # Open image to check format and potentially convert
            with Image.open(image_path) as img:
                # img2pdf doesn't support all formats, convert to PNG if needed
                if img.format not in ['JPEG', 'PNG', 'TIFF']:
                    # Convert to PNG
                    temp_png = self.cache_dir / f"temp_{image_path.stem}.png"
                    img.save(temp_png, 'PNG')
                    image_to_convert = temp_png
                else:
                    image_to_convert = image_path

            # Convert to PDF
            with open(image_to_convert, "rb") as img_file:
                pdf_bytes = img2pdf.convert(img_file)

            with open(output_path, "wb") as pdf_file:
                pdf_file.write(pdf_bytes)

            logger.info(f"Image conversion completed: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Image to PDF conversion failed: {e}")
            raise StirlingAPIError(f"Image to PDF conversion failed: {e}") from e

    def pdf_to_json(
        self, pdf_path: Path, lazy_load: bool = False
    ) -> Dict[str, Any]:
        """Extract PDF to JSON using pdfplumber.

        Args:
            pdf_path: Path to input PDF
            lazy_load: Not used in local implementation

        Returns:
            JSON structure with text, lines, rectangles, and curves

        Raises:
            StirlingAPIError: If extraction fails
        """
        logger.info(f"Extracting PDF to JSON: {pdf_path.name}")

        try:
            pages_data = []

            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_width = page.width
                    page_height = page.height

                    # Extract text elements
                    text_elements = []
                    words = page.extract_words(
                        keep_blank_chars=True,
                        extra_attrs=['fontname', 'size']
                    )

                    for word in words:
                        text = word.get("text", "")
                        
                        # Filter out CID codes (e.g., "(cid:13)", "(cid:136)")
                        # These are placeholder codes for embedded font glyphs
                        import re
                        text = re.sub(r'\(cid:\d+\)', '', text).strip()
                        
                        # Skip if text is empty after filtering
                        if not text:
                            continue
                        
                        text_elem = {
                            "text": text,
                            "x": float(word.get("x0", 0)),
                            "y": float(word.get("top", 0)),
                            "width": float(word.get("x1", 0) - word.get("x0", 0)),
                            "height": float(word.get("bottom", 0) - word.get("top", 0)),
                            "fontSize": float(word.get("size", 12)) if word.get("size") else 12.0,
                            "fontName": word.get("fontname", "Helvetica"),
                        }
                        text_elements.append(text_elem)

                    # Extract lines
                    line_elements = []
                    for line in page.lines:
                        line_elem = {
                            "x0": float(line.get("x0", 0)),
                            "y0": float(line.get("top", 0)),
                            "x1": float(line.get("x1", 0)),
                            "y1": float(line.get("bottom", 0)),
                            "lineWidth": float(line.get("linewidth", 1) or 1),
                            "strokeColor": self._extract_color(line.get("stroking_color")),
                        }
                        line_elements.append(line_elem)

                    # Extract rectangles
                    rect_elements = []
                    for rect in page.rects:
                        rect_elem = {
                            "x0": float(rect.get("x0", 0)),
                            "y0": float(rect.get("top", 0)),
                            "x1": float(rect.get("x1", 0)),
                            "y1": float(rect.get("bottom", 0)),
                            "lineWidth": float(rect.get("linewidth", 1) or 1),
                            "strokeColor": self._extract_color(rect.get("stroking_color")),
                            "fillColor": self._extract_color(rect.get("non_stroking_color")),
                        }
                        rect_elements.append(rect_elem)

                    # Extract curves
                    curve_elements = []
                    for curve in page.curves:
                        # Curves have a 'pts' attribute with list of points
                        pts = curve.get("pts", [])
                        if pts:
                            curve_elem = {
                                "points": [(float(p[0]), float(p[1])) for p in pts],
                                "lineWidth": float(curve.get("linewidth", 1) or 1),
                                "strokeColor": self._extract_color(curve.get("stroking_color")),
                                "fillColor": self._extract_color(curve.get("non_stroking_color")),
                            }
                            curve_elements.append(curve_elem)

                    page_data = {
                        "pageNumber": page_num,
                        "width": float(page_width),
                        "height": float(page_height),
                        "textElements": text_elements,
                        "lineElements": line_elements,
                        "rectElements": rect_elements,
                        "curveElements": curve_elements,
                    }
                    pages_data.append(page_data)

            pdf_json = {"pages": pages_data}

            total_text = sum(len(p["textElements"]) for p in pages_data)
            total_lines = sum(len(p["lineElements"]) for p in pages_data)
            total_rects = sum(len(p["rectElements"]) for p in pages_data)
            total_curves = sum(len(p["curveElements"]) for p in pages_data)
            logger.info(
                f"PDF extracted to JSON: {len(pages_data)} pages, "
                f"{total_text} text, {total_lines} lines, {total_rects} rects, {total_curves} curves"
            )
            return pdf_json

        except Exception as e:
            logger.error(f"PDF to JSON extraction failed: {e}")
            raise StirlingAPIError(f"PDF to JSON extraction failed: {e}") from e

    def _extract_color(self, color) -> list | None:
        """Extract color as RGB list from pdfplumber color value.

        Args:
            color: Color value from pdfplumber (tuple, list, or None)

        Returns:
            RGB color as [r, g, b] with values 0-1, or None
        """
        if color is None:
            return None
        if isinstance(color, (list, tuple)):
            # Convert to list of floats
            return [float(c) for c in color[:3]] if len(color) >= 3 else [0, 0, 0]
        return None

    def json_to_pdf(
        self, json_data: Dict[str, Any], output_path: Path, 
        resolve_collisions: bool = False,
        add_word_spacing: bool = False
    ) -> Path:
        """Rebuild PDF from JSON using reportlab.

        Args:
            json_data: JSON structure with pages, textElements, lineElements, rectElements, curveElements
            output_path: Path to save output PDF
            resolve_collisions: If True, detect and resolve overlapping text by cascading shifts
            add_word_spacing: If True, add minimum spacing between adjacent words (can be aggressive)

        Returns:
            Path to generated PDF

        Raises:
            StirlingAPIError: If PDF generation fails
        """
        logger.info(f"Rebuilding PDF from JSON to {output_path.name} (resolve_collisions={resolve_collisions}, add_word_spacing={add_word_spacing})")

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            pages = json_data.get("pages", [])
            if not pages:
                raise StirlingAPIError("No pages found in JSON data")

            # Get first page dimensions for default page size
            first_page = pages[0]
            page_width = first_page.get("width", 612)  # Default letter width
            page_height = first_page.get("height", 792)  # Default letter height

            c = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))

            for page_data in pages:
                page_w = page_data.get("width", page_width)
                page_h = page_data.get("height", page_height)
                c.setPageSize((page_w, page_h))

                # 1. Draw rectangles first (background)
                for rect in page_data.get("rectElements", []):
                    x0 = rect.get("x0", 0)
                    y0_top = rect.get("y0", 0)
                    x1 = rect.get("x1", 0)
                    y1_top = rect.get("y1", 0)
                    
                    # Convert from top-left to bottom-left coordinates
                    y0 = page_h - y1_top
                    y1 = page_h - y0_top
                    
                    line_width = rect.get("lineWidth", 1)
                    stroke_color = rect.get("strokeColor")
                    fill_color = rect.get("fillColor")
                    
                    c.setLineWidth(line_width)
                    
                    if stroke_color:
                        c.setStrokeColorRGB(*stroke_color[:3])
                    else:
                        c.setStrokeColorRGB(0, 0, 0)
                    
                    if fill_color:
                        c.setFillColorRGB(*fill_color[:3])
                        c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=1)
                    else:
                        c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)

                # 2. Draw lines
                for line in page_data.get("lineElements", []):
                    x0 = line.get("x0", 0)
                    y0_top = line.get("y0", 0)
                    x1 = line.get("x1", 0)
                    y1_top = line.get("y1", 0)
                    
                    # Convert from top-left to bottom-left coordinates
                    y0 = page_h - y0_top
                    y1 = page_h - y1_top
                    
                    line_width = line.get("lineWidth", 1)
                    stroke_color = line.get("strokeColor")
                    
                    c.setLineWidth(line_width)
                    
                    if stroke_color:
                        c.setStrokeColorRGB(*stroke_color[:3])
                    else:
                        c.setStrokeColorRGB(0, 0, 0)
                    
                    c.line(x0, y0, x1, y1)

                # 3. Draw curves (as connected lines)
                for curve in page_data.get("curveElements", []):
                    points = curve.get("points", [])
                    if len(points) < 2:
                        continue
                    
                    line_width = curve.get("lineWidth", 1)
                    stroke_color = curve.get("strokeColor")
                    
                    c.setLineWidth(line_width)
                    
                    if stroke_color:
                        c.setStrokeColorRGB(*stroke_color[:3])
                    else:
                        c.setStrokeColorRGB(0, 0, 0)
                    
                    # Create path
                    path = c.beginPath()
                    first_point = points[0]
                    path.moveTo(first_point[0], page_h - first_point[1])
                    
                    for point in points[1:]:
                        path.lineTo(point[0], page_h - point[1])
                    
                    c.drawPath(path, stroke=1, fill=0)

                # 4. Draw text elements on top
                c.setFillColorRGB(0, 0, 0)  # Reset fill color for text
                
                text_elements = page_data.get("textElements", [])
                
                # Apply collision resolution if enabled
                if resolve_collisions and text_elements:
                    text_elements = self._resolve_text_collisions(text_elements, page_w, page_h)
                
                # Apply word spacing if enabled (separate from collision resolution)
                if add_word_spacing and text_elements:
                    text_elements = self._add_word_spacing(text_elements, page_w)
                
                for elem in text_elements:
                    text = elem.get("text", "")
                    if not text:
                        continue

                    x = elem.get("x", 0)
                    # PDF coordinates are from bottom-left, pdfplumber gives top-left
                    y_from_top = elem.get("y", 0)
                    elem_height = elem.get("height", 12)
                    y = page_h - y_from_top - elem_height

                    font_size = elem.get("fontSize", 12)
                    font_name = elem.get("fontName", "Helvetica")

                    # Use standard fonts to avoid font not found errors
                    safe_font = self._get_safe_font(font_name)

                    try:
                        c.setFont(safe_font, font_size)
                    except Exception:
                        c.setFont("Helvetica", font_size)

                    c.drawString(x, y, text)

                c.showPage()

            c.save()

            logger.info(f"PDF generated successfully: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"JSON to PDF generation failed: {e}")
            raise StirlingAPIError(f"JSON to PDF generation failed: {e}") from e

    def _get_safe_font(self, font_name: str) -> str:
        """Map font name to a safe reportlab font.

        Args:
            font_name: Original font name from PDF

        Returns:
            Safe font name that reportlab can use
        """
        # Standard fonts available in reportlab
        font_map = {
            "helvetica": "Helvetica",
            "arial": "Helvetica",
            "times": "Times-Roman",
            "timesnewroman": "Times-Roman",
            "times-roman": "Times-Roman",
            "courier": "Courier",
            "symbol": "Symbol",
            "zapfdingbats": "ZapfDingbats",
        }

        # Normalize font name
        normalized = font_name.lower().replace(" ", "").replace("-", "")

        # Check for bold/italic variants
        if "bold" in normalized and "italic" in normalized:
            if "times" in normalized:
                return "Times-BoldItalic"
            elif "courier" in normalized:
                return "Courier-BoldOblique"
            return "Helvetica-BoldOblique"
        elif "bold" in normalized:
            if "times" in normalized:
                return "Times-Bold"
            elif "courier" in normalized:
                return "Courier-Bold"
            return "Helvetica-Bold"
        elif "italic" in normalized or "oblique" in normalized:
            if "times" in normalized:
                return "Times-Italic"
            elif "courier" in normalized:
                return "Courier-Oblique"
            return "Helvetica-Oblique"

        # Match base font
        for key, value in font_map.items():
            if key in normalized:
                return value

        # Default to Helvetica
        return "Helvetica"

    def _resolve_text_collisions(
        self, elements: list, page_width: float, page_height: float
    ) -> list:
        """Resolve overlapping text elements by cascading shifts.

        Args:
            elements: List of text element dicts with x, y, width, height, fontSize
            page_width: Page width for boundary checking
            page_height: Page height for boundary checking

        Returns:
            New list of elements with adjusted positions
        """
        if not elements:
            return elements

        # Deep copy to avoid modifying original
        import copy
        resolved = copy.deepcopy(elements)

        # Sort by y (top to bottom), then x (left to right)
        resolved.sort(key=lambda e: (e.get("y", 0), e.get("x", 0)))

        # Track occupied regions: (x, y, w, h, font_size)
        occupied = []

        for i, elem in enumerate(resolved):
            x = elem.get("x", 0)
            y = elem.get("y", 0)
            w = elem.get("width", 50)
            h = elem.get("height", 12)
            font_size = elem.get("fontSize", 12)
            
            # Margin based on font size (larger fonts need more space)
            base_margin = max(font_size * 0.3, 2)

            # Check collision with all occupied regions
            shift_y = 0
            shift_x = 0
            
            for ox, oy, ow, oh, o_font_size in occupied:
                # Use the larger font size for margin calculation
                margin = max(font_size, o_font_size) * 0.3
                margin = max(margin, 3)  # Minimum 3 units
                
                # Check if boxes overlap (with margin)
                x_overlap = (x < ox + ow + margin) and (x + w + margin > ox)
                y_overlap = (y < oy + oh + margin) and (y + h + margin > oy)
                
                if x_overlap and y_overlap:
                    # Calculate if it's more of a vertical or horizontal overlap
                    x_overlap_amount = min(x + w, ox + ow) - max(x, ox)
                    y_overlap_amount = min(y + h, oy + oh) - max(y, oy)
                    
                    if y_overlap_amount <= h * 0.5:
                        # Partial vertical overlap - shift down
                        needed_shift_y = (oy + oh + margin) - y
                        shift_y = max(shift_y, needed_shift_y)
                    else:
                        # Same line - shift right
                        needed_shift_x = (ox + ow + margin) - x
                        if needed_shift_x > 0:
                            shift_x = max(shift_x, needed_shift_x)

            # Apply horizontal shift to this element only
            if shift_x > 0:
                new_x = x + shift_x
                # Clamp to page bounds
                new_x = min(new_x, page_width - w - base_margin)
                new_x = max(new_x, 0)
                resolved[i]["x"] = new_x

            # Apply vertical shift to this and all subsequent elements
            if shift_y > 0:
                for j in range(i, len(resolved)):
                    old_y = resolved[j].get("y", 0)
                    new_y = old_y + shift_y
                    # Clamp to page bounds
                    elem_h = resolved[j].get("height", 12)
                    new_y = min(new_y, page_height - elem_h - base_margin)
                    new_y = max(new_y, 0)
                    resolved[j]["y"] = new_y

            # Add this element to occupied regions (with updated position)
            final_x = resolved[i].get("x", 0)
            final_y = resolved[i].get("y", 0)
            occupied.append((final_x, final_y, w, h, font_size))

        logger.debug(f"Collision resolution applied to {len(resolved)} elements")
        return resolved

    def _add_word_spacing(self, elements: list, page_width: float) -> list:
        """Add minimum spacing between horizontally adjacent words on the same line.
        
        Args:
            elements: List of text elements
            page_width: Page width for bounds checking
            
        Returns:
            Elements with adjusted horizontal spacing
        """
        if len(elements) < 2:
            return elements
        
        # Group elements by approximate Y position (same line = within 5 units)
        line_tolerance = 5
        lines = {}
        
        for i, elem in enumerate(elements):
            y = elem.get("y", 0)
            # Find or create line group
            line_key = None
            for key in lines:
                if abs(key - y) < line_tolerance:
                    line_key = key
                    break
            if line_key is None:
                line_key = y
                lines[line_key] = []
            lines[line_key].append(i)
        
        # For each line, sort by X and ensure minimum spacing
        for line_y, indices in lines.items():
            if len(indices) < 2:
                continue
            
            # Sort indices by X position
            indices.sort(key=lambda i: elements[i].get("x", 0))
            
            # Calculate cumulative shift needed
            cumulative_shift = 0
            
            for j in range(1, len(indices)):
                prev_idx = indices[j - 1]
                curr_idx = indices[j]
                
                prev_elem = elements[prev_idx]
                curr_elem = elements[curr_idx]
                
                prev_x = prev_elem.get("x", 0) + cumulative_shift
                prev_w = prev_elem.get("width", 50)
                prev_font = prev_elem.get("fontSize", 12)
                
                curr_x = curr_elem.get("x", 0)
                curr_font = curr_elem.get("fontSize", 12)
                
                # Minimum space between words (based on average font size)
                avg_font = (prev_font + curr_font) / 2
                min_space = avg_font * 0.4  # ~40% of font size as word gap
                min_space = max(min_space, 4)  # At least 4 units
                
                # Current gap between words
                current_gap = curr_x - (prev_x + prev_w)
                
                # If gap is too small, shift this and all subsequent words on this line
                if current_gap < min_space:
                    shift_needed = min_space - current_gap
                    cumulative_shift += shift_needed
                    
                    # Apply shift to current and all subsequent elements on this line
                    for k in range(j, len(indices)):
                        idx = indices[k]
                        old_x = elements[idx].get("x", 0)
                        new_x = old_x + shift_needed
                        # Clamp to page bounds
                        elem_w = elements[idx].get("width", 50)
                        new_x = min(new_x, page_width - elem_w - 2)
                        elements[idx]["x"] = new_x
        
        return elements

    def get_page_json(self, job_id: str, page_number: int) -> Dict[str, Any]:
        """Get single page JSON - not implemented for local client.

        This method exists for API compatibility but lazy loading
        is not supported in the local implementation.
        """
        raise NotImplementedError(
            "Lazy loading not supported in local client. "
            "Use pdf_to_json with lazy_load=False instead."
        )
