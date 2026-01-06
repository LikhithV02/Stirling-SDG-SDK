"""JSON navigation utilities."""

from typing import Any, Dict, List


class JSONNavigator:
    """Helper utilities for traversing PDF JSON structure."""

    @staticmethod
    def find_element_by_text(
        pdf_json: Dict[str, Any], text: str, page_number: int | None = None
    ) -> List[Dict[str, Any]]:
        """Find text elements matching given text.

        Args:
            pdf_json: PDF JSON structure
            text: Text to search for
            page_number: Optional page number to limit search (1-indexed)

        Returns:
            List of matching text elements with page info
        """
        matches = []

        pages = pdf_json.get("pages", [])
        for page in pages:
            current_page_num = page.get("number", 0)

            # Skip if page_number specified and doesn't match
            if page_number is not None and current_page_num != page_number:
                continue

            # Search text elements
            for elem in page.get("textElements", []):
                if text.strip().lower() in elem.get("text", "").strip().lower():
                    matches.append(
                        {
                            "pageNumber": current_page_num,
                            "element": elem,
                        }
                    )

        return matches

    @staticmethod
    def get_page(pdf_json: Dict[str, Any], page_number: int) -> Dict[str, Any] | None:
        """Get a specific page from PDF JSON.

        Args:
            pdf_json: PDF JSON structure
            page_number: Page number (1-indexed)

        Returns:
            Page dict or None if not found
        """
        pages = pdf_json.get("pages", [])
        for page in pages:
            if page.get("number") == page_number:
                return page
        return None

    @staticmethod
    def get_text_elements(page: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get all text elements from a page.

        Args:
            page: Page dict from PDF JSON

        Returns:
            List of text elements
        """
        return page.get("textElements", [])

    @staticmethod
    def count_total_elements(pdf_json: Dict[str, Any]) -> int:
        """Count total text elements across all pages.

        Args:
            pdf_json: PDF JSON structure

        Returns:
            Total number of text elements
        """
        total = 0
        for page in pdf_json.get("pages", []):
            total += len(page.get("textElements", []))
        return total
