"""Content classifier for identifying variable vs static fields."""

from typing import Any, Dict

from ..config.settings import Settings
from ..synthesis.github_models_client import GitHubModelsClient
from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


class ContentClassifier:
    """Classifies text elements in PDF JSON as variable vs static."""

    def __init__(self, settings: Settings | None = None):
        """Initialize classifier.

        Args:
            settings: Application settings (loads from env if not provided)
        """
        if settings is None:
            settings = Settings()

        self.settings = settings
        self.github_client = GitHubModelsClient(settings)

    def classify(self, pdf_json: Dict[str, Any]) -> Dict[str, Any]:
        """Classify which text elements are variable fields.

        Args:
            pdf_json: JSON structure from Stirling PDF

        Returns:
            Template with variable_fields list

        Example return:
            {
                "variable_fields": [
                    {
                        "pageNumber": 1,
                        "text": "John Smith",
                        "fieldType": "patient_name",
                        "dataType": "string"
                    }
                ],
                "metadata": {
                    "total_pages": 4,
                    "total_elements": 150,
                    "variable_count": 25,
                    "headers_excluded": 5
                }
            }
        """
        total_pages = len(pdf_json.get("pages", []))
        total_elements = sum(
            len(page.get("textElements", [])) for page in pdf_json.get("pages", [])
        )
        logger.info(
            f"Starting content classification: {total_pages} pages, {total_elements} text elements"
        )

        # Use GitHub Models client to classify
        logger.info(f"Sending PDF JSON to LLM for classification (model: {self.settings.github_model})")
        result = self.github_client.classify_content(pdf_json)

        # Add metadata
        variable_fields = result.get("variable_fields", [])
        headers_excluded = result.get("headers_excluded", 0)

        result["metadata"] = {
            "total_pages": total_pages,
            "total_elements": total_elements,
            "variable_count": len(variable_fields),
            "headers_excluded": headers_excluded,
        }

        logger.info(
            f"Classification complete: {len(variable_fields)} variable fields "
            f"out of {total_elements} total elements "
            f"({len(variable_fields)/total_elements*100:.1f}%), "
            f"{headers_excluded} headers excluded"
        )

        return result
