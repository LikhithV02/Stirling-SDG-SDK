"""Stirling PDF client module.

This module provides a unified interface for PDF processing operations.
By default, it uses LocalStirlingClient which processes PDFs locally using
Python libraries. The legacy HTTP-based StirlingHTTPClient is available
for backward compatibility with Stirling PDF Docker containers.
"""

from pathlib import Path
from typing import Any, Dict

from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


def get_stirling_client(
    use_local: bool = True,
    base_url: str = "http://localhost:8080",
    timeout: int = 300,
    api_key: str | None = None,
    cache_dir: Path | None = None,
):
    """Factory function to get the appropriate Stirling client.

    Args:
        use_local: If True, use local Python libraries (default).
                   If False, use HTTP client to connect to Stirling PDF Docker.
        base_url: Base URL for Stirling PDF API (only used if use_local=False)
        timeout: Request timeout in seconds (only used if use_local=False)
        api_key: Optional API key for authentication (only used if use_local=False)
        cache_dir: Directory for cached files (only used if use_local=True)

    Returns:
        StirlingClient instance (either LocalStirlingClient or StirlingHTTPClient)
    """
    if use_local:
        from .local_client import LocalStirlingClient
        return LocalStirlingClient(cache_dir=cache_dir)
    else:
        from .http_client import StirlingHTTPClient
        return StirlingHTTPClient(
            base_url=base_url,
            timeout=timeout,
            api_key=api_key,
        )


# Default export: LocalStirlingClient as StirlingClient for backward compatibility
from .local_client import LocalStirlingClient as StirlingClient

__all__ = ["StirlingClient", "get_stirling_client"]
