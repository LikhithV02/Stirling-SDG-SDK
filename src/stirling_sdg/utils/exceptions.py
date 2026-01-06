"""Custom exceptions for Stirling PDF SDG."""


class StirlingSDGError(Exception):
    """Base exception for all Stirling PDF SDG errors."""

    pass


class StirlingAPIError(StirlingSDGError):
    """Exception raised for Stirling PDF API errors."""

    pass


class ConfigurationError(StirlingSDGError):
    """Exception raised for configuration errors."""

    pass


class PDFProcessingError(StirlingSDGError):
    """Exception raised for PDF processing errors."""

    pass


class LLMError(StirlingSDGError):
    """Exception raised for LLM-related errors."""

    pass


class ClassificationError(LLMError):
    """Exception raised for classification errors."""

    pass


class SynthesisError(LLMError):
    """Exception raised for synthesis errors."""

    pass
