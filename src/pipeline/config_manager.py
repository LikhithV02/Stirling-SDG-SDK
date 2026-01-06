"""Configuration manager for pipeline templates and settings."""

import json
from pathlib import Path
from typing import Any, Dict

import yaml

from ..config.settings import Settings
from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


class ConfigManager:
    """Manages pipeline configurations and templates."""

    def __init__(self, settings: Settings | None = None):
        """Initialize config manager.

        Args:
            settings: Application settings (loads from env if not provided)
        """
        if settings is None:
            settings = Settings()

        self.settings = settings
        self.pipeline_dir = settings.config_dir / "pipeline_templates"
        self.template_dir = settings.config_dir / "templates"

        # Ensure directories exist
        self.pipeline_dir.mkdir(parents=True, exist_ok=True)
        self.template_dir.mkdir(parents=True, exist_ok=True)

    def save_pipeline_config(self, name: str, config: Dict[str, Any]):
        """Save pipeline configuration as YAML.

        Args:
            name: Configuration name
            config: Pipeline configuration dict

        Example config:
            {
                "name": "Medical Form Pipeline",
                "version": "1.0",
                "steps": {
                    "detect_input": {"enabled": true},
                    "ocr_conversion": {
                        "enabled": true,
                        "languages": ["eng"],
                        "skip_if_digital": true
                    },
                    "classify_content": {
                        "enabled": true,
                        "temperature": 0.3
                    },
                    "generate_synthetic": {
                        "enabled": true,
                        "temperature": 0.9
                    }
                },
                "batch": {
                    "enabled": true,
                    "num_variations": 100,
                    "reuse_template": true
                }
            }
        """
        config_path = self.pipeline_dir / f"{name}.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Pipeline config saved: {config_path}")

    def load_pipeline_config(self, name: str) -> Dict[str, Any]:
        """Load pipeline configuration from YAML.

        Args:
            name: Configuration name

        Returns:
            Pipeline configuration dict

        Raises:
            FileNotFoundError: If configuration doesn't exist
        """
        config_path = self.pipeline_dir / f"{name}.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Pipeline config not found: {config_path}")

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        logger.info(f"Pipeline config loaded: {config_path}")
        return config

    def list_pipeline_configs(self) -> list[str]:
        """List available pipeline configurations.

        Returns:
            List of configuration names
        """
        configs = []
        for path in self.pipeline_dir.glob("*.yaml"):
            configs.append(path.stem)
        return sorted(configs)

    def save_template(self, name: str, template: Dict[str, Any]):
        """Save classification template as JSON.

        Args:
            name: Template name
            template: Classification template dict
        """
        template_path = self.template_dir / f"{name}_template.json"
        with open(template_path, "w") as f:
            json.dump(template, f, indent=2)
        logger.info(f"Template saved: {template_path}")

    def load_template(self, name: str) -> Dict[str, Any]:
        """Load classification template from JSON.

        Args:
            name: Template name (without _template.json suffix)

        Returns:
            Classification template dict

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        template_path = self.template_dir / f"{name}_template.json"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        with open(template_path, "r") as f:
            template = json.load(f)
        logger.info(f"Template loaded: {template_path}")
        return template

    def list_templates(self) -> list[str]:
        """List available classification templates.

        Returns:
            List of template names
        """
        templates = []
        for path in self.template_dir.glob("*_template.json"):
            # Remove _template.json suffix
            name = path.stem.replace("_template", "")
            templates.append(name)
        return sorted(templates)

    def create_default_pipeline(self):
        """Create a default pipeline configuration."""
        default_config = {
            "name": "Default Medical Form Pipeline",
            "version": "1.0",
            "description": "Standard pipeline for medical forms with OCR and synthetic data generation",
            "steps": {
                "detect_input": {"enabled": True},
                "ocr_conversion": {
                    "enabled": True,
                    "languages": ["eng"],
                    "skip_if_digital": True,
                },
                "extract_text": {"enabled": True},
                "classify_content": {
                    "enabled": True,
                    "temperature": 0.3,
                    "confidence_threshold": 0.7,
                },
                "generate_synthetic": {
                    "enabled": True,
                    "temperature": 0.9,
                    "diversity_level": "high",
                },
                "create_output": {
                    "enabled": True,
                    "flatten": True,
                },
            },
            "batch": {
                "enabled": True,
                "num_variations": 100,
                "parallel_workers": 4,
                "reuse_template": True,
            },
        }

        self.save_pipeline_config("default", default_config)
        logger.info("Default pipeline config created")
        return default_config
