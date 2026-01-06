"""Stirling PDF HTTP API client (Legacy).

This module provides the HTTP-based client for connecting to a Stirling PDF
Docker container. It is kept for backward compatibility.

For new implementations, use LocalStirlingClient from local_client.py instead.
"""

import time
from pathlib import Path
from typing import Dict, Any

import requests

from ..utils.exceptions import StirlingAPIError
from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


class StirlingHTTPClient:
    """HTTP client for interacting with Stirling PDF API (Legacy).
    
    This client requires a running Stirling PDF Docker container.
    Consider using LocalStirlingClient for a Docker-free experience.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: int = 300,
        api_key: str | None = None,
    ):
        """Initialize Stirling PDF HTTP client.

        Args:
            base_url: Base URL for Stirling PDF API
            timeout: Request timeout in seconds
            api_key: Optional API key for authentication (X-API-KEY header)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        self._check_connection()

    def _check_connection(self):
        """Check if Stirling PDF API is reachable."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/info/status", timeout=10
            )
            if response.status_code == 200:
                info = response.json()
                logger.info(
                    f"Connected to Stirling PDF {info.get('version', 'unknown')} - Status: {info.get('status', 'unknown')}"
                )
            else:
                logger.warning(
                    f"Stirling PDF responded with status {response.status_code}"
                )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Cannot connect to Stirling PDF at {self.base_url}: {e}"
            )
            raise StirlingAPIError(
                f"Stirling PDF not reachable at {self.base_url}. "
                f"Is it running? Try: docker run -p 8080:8080 stirlingtools/stirling-pdf:latest"
            ) from e

    def _make_request(
        self,
        endpoint: str,
        files: Dict[str, Any] | None = None,
        data: Dict[str, Any] | None = None,
        json: Dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> bytes:
        """Make API request with retry logic.

        Args:
            endpoint: API endpoint path
            files: Files to upload (multipart/form-data)
            data: Form data parameters
            json: JSON payload
            max_retries: Maximum number of retry attempts

        Returns:
            Binary response content

        Raises:
            StirlingAPIError: If request fails after retries
        """
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"Making request to {endpoint}")

        # Prepare headers with optional API key
        headers = {}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key

        for attempt in range(max_retries):
            try:
                if json is not None:
                    # JSON request
                    headers["Content-Type"] = "application/json"
                    response = requests.post(
                        url, json=json, headers=headers, timeout=self.timeout
                    )
                else:
                    # Multipart/form-data request
                    response = requests.post(
                        url,
                        files=files,
                        data=data,
                        headers=headers if headers else None,
                        timeout=self.timeout,
                    )

                # Check response status
                if response.status_code == 200:
                    response_size = len(response.content)
                    logger.debug(
                        f"Request successful: {endpoint} - Response size: {response_size} bytes "
                        f"({response_size / 1024:.1f} KB)"
                    )
                    return response.content

                elif response.status_code == 500:
                    error_msg = f"Stirling PDF server error: {response.text}"
                    logger.error(error_msg)
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.info(
                            f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue
                    raise StirlingAPIError(error_msg)

                elif response.status_code == 404:
                    raise StirlingAPIError(f"Endpoint not found: {endpoint}")

                else:
                    raise StirlingAPIError(
                        f"Unexpected status {response.status_code}: {response.text}"
                    )

            except requests.Timeout:
                logger.warning(
                    f"Request timeout (attempt {attempt + 1}/{max_retries})"
                )
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                raise StirlingAPIError("Request timeout")

            except requests.ConnectionError as e:
                logger.error("Connection error to Stirling PDF API")
                raise StirlingAPIError(
                    f"Cannot connect to Stirling PDF. Is it running on {self.base_url}?"
                ) from e

        raise StirlingAPIError("Max retries exceeded")

    def ocr_pdf(
        self,
        input_path: Path,
        languages: list[str] | None = None,
        ocr_type: str = "skip-text",
    ) -> Path:
        """Apply OCR to PDF using Stirling PDF API.

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
        logger.info(
            f"Applying OCR to {input_path.name} ({file_size / 1024:.1f} KB, languages: {','.join(languages)})"
        )

        with open(input_path, "rb") as f:
            files = {"fileInput": (input_path.name, f, "application/pdf")}
            data = {
                "languages": ",".join(languages),
                "ocrRenderType": "hocr",  # Searchable text layer
                "ocrType": ocr_type,
            }

            response_content = self._make_request(
                "/api/v1/misc/ocr-pdf", files=files, data=data
            )

        # Save to cache
        from ..config.settings import Settings

        settings = Settings()
        output_path = settings.cache_dir / f"ocr_{input_path.stem}.pdf"
        with open(output_path, "wb") as f:
            f.write(response_content)

        logger.info(f"OCR completed: {output_path}")
        return output_path

    def convert_image_to_pdf(self, image_path: Path) -> Path:
        """Convert image to PDF using Stirling PDF API.

        Args:
            image_path: Path to input image

        Returns:
            Path to converted PDF (saved in cache)

        Raises:
            StirlingAPIError: If conversion fails
        """
        file_size = image_path.stat().st_size
        logger.info(f"Converting image to PDF: {image_path.name} ({file_size / 1024:.1f} KB)")

        # Detect MIME type
        suffix = image_path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(suffix, "image/png")

        with open(image_path, "rb") as f:
            files = {"fileInput": (image_path.name, f, mime_type)}

            response_content = self._make_request(
                "/api/v1/convert/img/pdf", files=files
            )

        # Save to cache
        from ..config.settings import Settings

        settings = Settings()
        output_path = settings.cache_dir / f"converted_{image_path.stem}.pdf"
        with open(output_path, "wb") as f:
            f.write(response_content)

        logger.info(f"Image conversion completed: {output_path}")
        return output_path

    def pdf_to_json(
        self, pdf_path: Path, lazy_load: bool = False
    ) -> Dict[str, Any]:
        """Extract PDF to JSON using Stirling Text Editor API.

        Args:
            pdf_path: Path to input PDF
            lazy_load: If True, returns job_id for large PDFs

        Returns:
            JSON structure with text, positions, fonts, styling

        Raises:
            StirlingAPIError: If extraction fails
        """
        logger.info(f"Extracting PDF to JSON: {pdf_path.name}")

        with open(pdf_path, "rb") as f:
            files = {"fileInput": (pdf_path.name, f, "application/pdf")}
            data = {"lazyLoad": "true" if lazy_load else "false"}

            response_content = self._make_request(
                "/api/v1/convert/pdf/text-editor", files=files, data=data
            )

        # Parse JSON response
        import json

        try:
            pdf_json = json.loads(response_content.decode("utf-8"))
            logger.info(
                f"PDF extracted to JSON: {len(pdf_json.get('pages', []))} pages"
            )
            return pdf_json
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise StirlingAPIError(
                f"Invalid JSON response from Stirling PDF: {e}"
            ) from e

    def json_to_pdf(self, json_data: Dict[str, Any], output_path: Path) -> Path:
        """Rebuild PDF from modified JSON using Stirling Text Editor API.

        Args:
            json_data: Modified JSON structure
            output_path: Path to save output PDF

        Returns:
            Path to generated PDF

        Raises:
            StirlingAPIError: If PDF generation fails
        """
        logger.info(f"Rebuilding PDF from JSON to {output_path.name}")

        # Convert JSON dict to bytes
        import json

        json_bytes = json.dumps(json_data).encode("utf-8")

        # Send as file upload
        files = {"fileInput": ("document.json", json_bytes, "application/json")}

        response_content = self._make_request(
            "/api/v1/convert/text-editor/pdf", files=files
        )

        # Save PDF
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response_content)

        # Verify it's a valid PDF
        try:
            import fitz  # PyMuPDF for validation only

            doc = fitz.open(output_path)
            doc.close()
            logger.info(f"PDF generated successfully: {output_path}")
        except Exception:
            # PyMuPDF not available or PDF invalid, skip validation
            logger.info(f"PDF generated (validation skipped): {output_path}")

        return output_path

    def get_page_json(self, job_id: str, page_number: int) -> Dict[str, Any]:
        """Get single page JSON for lazy loading.

        Args:
            job_id: Job ID from pdf_to_json with lazy_load=True
            page_number: Page number to fetch (1-indexed)

        Returns:
            JSON structure for single page

        Raises:
            StirlingAPIError: If page fetch fails
        """
        logger.debug(f"Fetching page {page_number} for job {job_id}")

        response_content = self._make_request(
            f"/api/v1/convert/pdf/text-editor/page/{job_id}/{page_number}",
            files={},
        )

        import json

        try:
            return json.loads(response_content.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise StirlingAPIError(
                f"Invalid JSON response for page {page_number}: {e}"
            ) from e
