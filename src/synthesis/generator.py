"""Synthetic data generator."""

from typing import Any, Dict

from ..config.settings import Settings
from .github_models_client import GitHubModelsClient
from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


class SyntheticDataGenerator:
    """Generates coherent synthetic data for variable fields."""

    def __init__(self, settings: Settings | None = None):
        """Initialize generator.

        Args:
            settings: Application settings (loads from env if not provided)
        """
        if settings is None:
            settings = Settings()

        self.settings = settings
        self.github_client = GitHubModelsClient(settings)

    def generate(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Generate synthetic data for all variable fields in template.

        Args:
            template: Classification result with variable_fields

        Returns:
            Dict mapping field_type to synthetic value

        Example return:
            {
                "patient_name": "María García",
                "date_of_birth": "07/15/1975",
                "age": "48",
                "phone_number": "(555) 123-4567",
                "mrn": "MRN87654321"
            }
        """
        variable_fields = template.get("variable_fields", [])
        field_types = list(set(field["fieldType"] for field in variable_fields))

        logger.info(f"Generating synthetic data for {len(variable_fields)} fields ({len(field_types)} unique types)")
        logger.debug(f"Field types to generate: {field_types}")

        # Use GitHub Models client to generate
        logger.info(f"Sending template to LLM for data generation (model: {self.settings.github_model})")
        synthetic_data = self.github_client.generate_synthetic_data(template)

        logger.info(
            f"Generated synthetic data for {len(synthetic_data)} field types: {list(synthetic_data.keys())}"
        )

        return synthetic_data
