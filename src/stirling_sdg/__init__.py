"""Stirling PDF Synthetic Data Generator.

A Python SDK for generating synthetic data PDFs using native PDF processing
and GitHub Models API for LLM-based classification and data generation.

No Docker or external services required for PDF processing.
"""

__version__ = "0.2.0"

from .config.settings import Settings
from .stirling.client import StirlingClient
from .stirling.local_client import LocalStirlingClient
from .stirling.direct_edit_client import DirectEditClient
from .detection.detector import DocumentDetector
from .classification.classifier import ContentClassifier
from .synthesis.generator import SyntheticDataGenerator
from .json_editor.editor import JSONEditor
from .pipeline.orchestrator import PipelineOrchestrator
from .pipeline.config_manager import ConfigManager

__all__ = [
    "Settings",
    "StirlingClient",
    "LocalStirlingClient",
    "DirectEditClient",
    "DocumentDetector",
    "ContentClassifier",
    "SyntheticDataGenerator",
    "JSONEditor",
    "PipelineOrchestrator",
    "ConfigManager",
]

