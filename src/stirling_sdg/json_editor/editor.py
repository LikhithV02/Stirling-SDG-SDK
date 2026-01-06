"""JSON editor for replacing text values in Stirling PDF JSON."""

import copy
from typing import Any, Dict

from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


class JSONEditor:
    """Edits text values in Stirling PDF JSON structure."""

    def replace_text(
        self,
        pdf_json: Dict[str, Any],
        template: Dict[str, Any],
        synthetic_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Replace variable text elements with synthetic data.

        Args:
            pdf_json: Original PDF JSON from Stirling
            template: Classification result with variable_fields
            synthetic_data: Dict mapping field_type to synthetic value

        Returns:
            Modified JSON with synthetic text

        Example:
            pdf_json = {"pages": [{"textElements": [{"text": "John"}]}]}
            template = {"variable_fields": [{"pageNumber": 1, "text": "John", "fieldType": "name"}]}
            synthetic_data = {"name": "María"}
            -> Returns JSON with "John" replaced by "María"
        """
        variable_fields = template.get("variable_fields", [])
        logger.info(f"Starting text replacement: {len(variable_fields)} variable fields to replace")

        # Deep copy to avoid mutating original
        modified_json = copy.deepcopy(pdf_json)

        replacements_made = 0

        # Group variable fields by page for efficiency
        elements_by_page = {}
        for elem in variable_fields:
            page_num = elem.get("pageNumber", 1)
            # Safety check: ensure pageNumber is not None
            if page_num is None:
                logger.warning(f"pageNumber is None for element: {elem.get('text', 'UNKNOWN')}, defaulting to 1")
                page_num = 1
            if page_num not in elements_by_page:
                elements_by_page[page_num] = []
            elements_by_page[page_num].append(elem)

        logger.info(f"Fields grouped across {len(elements_by_page)} pages")

        # Process each page
        for page_num, page_elements in elements_by_page.items():
            logger.debug(f"Processing page {page_num} with {len(page_elements)} variable fields")
            # Find the corresponding page in JSON
            page_index = page_num - 1  # Pages are 1-indexed in template
            if page_index >= len(modified_json.get("pages", [])):
                logger.warning(f"Page {page_num} not found in PDF JSON")
                continue

            page = modified_json["pages"][page_index]
            text_elements = page.get("textElements", [])

            # Replace text for each variable element
            for var_elem in page_elements:
                original_text = var_elem.get("text", "")
                field_type = var_elem.get("fieldType")
                synthetic_value = synthetic_data.get(field_type)

                if synthetic_value is None:
                    logger.warning(
                        f"No synthetic value for field_type: {field_type}"
                    )
                    continue

                # Find and replace the text element
                # Strategy: find exact text match on this page
                replaced = False
                for text_elem in text_elements:
                    if text_elem.get("text", "").strip() == original_text.strip():
                        # Replace the text
                        old_text = text_elem["text"]
                        text_elem["text"] = str(synthetic_value)
                        replacements_made += 1
                        replaced = True
                        logger.debug(
                            f"Replaced '{old_text}' → '{synthetic_value}' "
                            f"(page {page_num}, field: {field_type})"
                        )
                        break  # Only replace first match

                if not replaced:
                    logger.warning(
                        f"Could not find text '{original_text}' on page {page_num}"
                    )

        logger.info(
            f"Text replacement complete: {replacements_made} replacements made"
        )

        return modified_json
