"""Configuration settings using Pydantic."""

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API Keys
    groq_api_key: str = Field(..., description="Groq API key (required)")
    github_token: str = Field(..., description="GitHub token for GitHub Models API (required)")
    stirling_api_key: str | None = Field(
        default=None, description="Stirling PDF API key (optional, for authenticated instances)"
    )

    # Stirling PDF
    stirling_pdf_url: str = Field(
        default="http://localhost:8080", description="Stirling PDF API base URL"
    )
    stirling_timeout: int = Field(
        default=300, description="Stirling PDF API timeout in seconds"
    )

    # LLM Settings
    groq_model: str = Field(
        default="openai/gpt-oss-120b", description="Groq model to use"
    )
    github_model: str = Field(
        default="openai/gpt-4o", description="GitHub Models model to use"
    )
    classification_temperature: float = Field(
        default=0.3, description="Temperature for classification LLM calls"
    )
    synthesis_temperature: float = Field(
        default=0.9, description="Temperature for synthesis LLM calls"
    )
    max_tokens_classification: int = Field(
        default=4096, description="Max tokens for classification"
    )
    max_tokens_synthesis: int = Field(
        default=500, description="Max tokens for synthesis"
    )

    # OCR Settings
    ocr_languages: str = Field(
        default="eng", description="OCR languages (comma-separated)"
    )
    ocr_render_type: str = Field(
        default="hocr", description="OCR render type (hocr or sandwich)"
    )

    # Processing
    pdf_dpi: int = Field(default=300, description="DPI for PDF/image processing")
    batch_size: int = Field(default=10, description="Batch processing size")

    # Paths
    data_dir: Path = Field(default=Path("./data"), description="Data directory")
    input_dir: Path = Field(
        default=Path("./data/input"), description="Input directory"
    )
    output_dir: Path = Field(
        default=Path("./data/output"), description="Output directory"
    )
    cache_dir: Path = Field(
        default=Path("./data/cache"), description="Cache directory"
    )
    config_dir: Path = Field(
        default=Path("./configs"), description="Config directory"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Path = Field(
        default=Path("./logs/stirling_sdg.log"), description="Log file path"
    )

    def __init__(self, **kwargs):
        """Initialize settings and create directories."""
        super().__init__(**kwargs)
        self._create_directories()

    def _create_directories(self):
        """Create necessary directories if they don't exist."""
        for path in [
            self.data_dir,
            self.input_dir,
            self.output_dir,
            self.cache_dir,
            self.config_dir,
            self.config_dir / "pipeline_templates",
            self.config_dir / "templates",
            self.log_file.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    @property
    def ocr_languages_list(self) -> List[str]:
        """Get OCR languages as a list."""
        return [lang.strip() for lang in self.ocr_languages.split(",")]
