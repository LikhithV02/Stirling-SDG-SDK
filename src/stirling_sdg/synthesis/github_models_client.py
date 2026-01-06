"""GitHub Models LLM client with token-efficient classification."""

import json
import os
import time
from typing import Any, Dict, List

from openai import OpenAI, RateLimitError

from ..config.settings import Settings
from ..utils.exceptions import LLMError, ClassificationError, SynthesisError
from ..utils.logging_utils import get_logger

logger = get_logger(__name__)

# Header detection threshold
HEADER_THRESHOLD = 18  # fontSize above this is considered a header


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, max_calls: int = 50, period: int = 60):
        """Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed
            period: Time period in seconds
        """
        self.max_calls = max_calls
        self.period = period
        self.calls: List[float] = []

    def wait_if_needed(self):
        """Wait if rate limit would be exceeded."""
        now = time.time()

        # Remove old calls outside the period
        self.calls = [t for t in self.calls if now - t < self.period]

        if len(self.calls) >= self.max_calls:
            # Calculate wait time
            oldest_call = self.calls[0]
            sleep_time = self.period - (now - oldest_call)
            if sleep_time > 0:
                logger.info(f"Rate limit reached, waiting {sleep_time:.1f}s")
                time.sleep(sleep_time)
                # Remove the oldest call after waiting
                self.calls.pop(0)

        # Record this call
        self.calls.append(time.time())


class GitHubModelsClient:
    """Client for GitHub Models API using OpenAI SDK."""

    def __init__(self, settings: Settings | None = None):
        """Initialize GitHub Models client.

        Args:
            settings: Application settings (loads from env if not provided)
        """
        if settings is None:
            settings = Settings()

        self.settings = settings
        self.client = OpenAI(
            base_url="https://models.github.ai/inference",
            api_key=settings.github_token,
        )
        self.rate_limiter = RateLimiter(max_calls=50, period=60)

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: Dict[str, str] | None = None,
        max_retries: int = 3,
    ) -> str:
        """Make a chat completion request with rate limiting and retries.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens in response
            response_format: Optional response format (e.g., {"type": "json_object"})
            max_retries: Maximum retry attempts

        Returns:
            Response content as string

        Raises:
            LLMError: If request fails after retries
        """
        # Calculate input size for logging
        input_chars = sum(len(msg.get("content", "")) for msg in messages)
        logger.debug(
            f"Preparing LLM request: {len(messages)} messages, {input_chars} chars, "
            f"model={self.settings.github_model}, temp={temperature}"
        )

        for attempt in range(max_retries):
            try:
                # Wait if needed for rate limiting
                self.rate_limiter.wait_if_needed()

                # Make request
                kwargs = {
                    "model": self.settings.github_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }

                if response_format:
                    kwargs["response_format"] = response_format

                logger.debug(f"Sending request to GitHub Models API (attempt {attempt + 1}/{max_retries})")
                response = self.client.chat.completions.create(**kwargs)

                content = response.choices[0].message.content

                # Log token usage if available
                if hasattr(response, 'usage') and response.usage:
                    logger.info(
                        f"LLM request complete - Tokens: {response.usage.total_tokens} total "
                        f"({response.usage.prompt_tokens} prompt + {response.usage.completion_tokens} completion), "
                        f"Response: {len(content)} chars"
                    )
                else:
                    logger.info(f"LLM request complete - Response: {len(content)} chars")

                logger.debug(f"LLM response preview: {content[:100]}...")
                return content

            except RateLimitError:
                wait_time = 2 ** attempt * 10  # Exponential backoff: 10s, 20s, 40s
                logger.warning(
                    f"Rate limit hit (attempt {attempt + 1}/{max_retries}), "
                    f"waiting {wait_time}s"
                )
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                raise LLMError("Rate limit exceeded after retries")

            except Exception as e:
                logger.error(f"LLM error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                raise LLMError(f"LLM request failed: {e}") from e

        raise LLMError("Max retries exceeded")

    def classify_content(
        self, pdf_json: Dict[str, Any], max_retries: int = 3
    ) -> Dict[str, Any]:
        """Classify text elements in PDF JSON as variable vs static.

        Args:
            pdf_json: JSON structure from Stirling PDF
            max_retries: Maximum retry attempts

        Returns:
            Classification result with variable_fields list

        Raises:
            ClassificationError: If classification fails
        """
        logger.info("Starting PDF content classification (text-only, token-efficient)...")

        # Prepare simplified JSON for LLM (text-only, no coordinates)
        logger.debug("Simplifying PDF JSON for classification")
        simplified_json, headers_excluded = self._simplify_json_for_classification(
            pdf_json
        )

        # Construct prompt
        system_prompt = """You are an expert at analyzing document structures and identifying variable vs static content.

Variable elements are data that changes per document instance:
- Names, dates, addresses, phone numbers, email addresses
- Medical record numbers, SSN, ID numbers
- Checkbox values, measurements, amounts, quantities
- Handwritten or typed patient/user data
- Form field values

Static elements are fixed content:
- Form labels, field names (e.g., "Patient Name:", "Date of Birth:")
- Instructions, legal text, disclaimers
- Headers, footers, page numbers
- Form structure and layout text
- Common words and phrases

Return ONLY valid JSON with no additional text."""

        user_prompt = f"""Analyze this PDF JSON structure and identify VARIABLE text elements.

Document text (page by page, text-only):
{json.dumps(simplified_json, separators=(',', ':'))}

Return JSON in this exact format. For EACH variable field you identify, you MUST include:
- "text": the exact text from the input
- "fieldType": descriptive name (lowercase_with_underscores)
- "dataType": one of: string, date, number, boolean
- "pageNumber": COPY THE EXACT pageNumber value from the input textElement (do not use null)

Example output format:
{{
  "variable_fields": [
    {{
      "text": "John Smith",
      "fieldType": "patient_name",
      "dataType": "string",
      "pageNumber": 1
    }},
    {{
      "text": "01/15/1980",
      "fieldType": "date_of_birth",
      "dataType": "date",
      "pageNumber": 1
    }}
  ]
}}

CRITICAL: The pageNumber field is REQUIRED and must be copied from the input - never use null."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response_content = self.chat_completion(
                messages=messages,
                temperature=self.settings.classification_temperature,
                max_tokens=self.settings.max_tokens_classification,
                response_format={"type": "json_object"},
                max_retries=max_retries,
            )

            # Parse JSON response
            logger.debug("Parsing classification response from LLM")
            try:
                # Sanitize response content to remove invalid escape sequences
                logger.debug("Sanitizing JSON response")
                response_content = self._sanitize_json_response(response_content)
                result = json.loads(response_content)
                variable_fields = result.get("variable_fields", [])

                # Post-process: fill in missing pageNumbers by matching text
                logger.debug("Post-processing: filling missing pageNumbers")
                result["variable_fields"] = self._fill_missing_page_numbers(
                    variable_fields, simplified_json
                )

                # Add headers_excluded to metadata
                result["headers_excluded"] = headers_excluded

                # Log classification result for debugging
                logger.debug(f"Classification result (after post-processing): {json.dumps(result, indent=2)}")

                logger.info(
                    f"Classification complete: {len(variable_fields)} variable fields found, "
                    f"{headers_excluded} headers excluded"
                )
                return result

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from LLM: {response_content[:200]}")
                raise ClassificationError(f"Invalid JSON response: {e}") from e

        except LLMError as e:
            raise ClassificationError(f"Classification failed: {e}") from e

    def generate_synthetic_data(
        self, template: Dict[str, Any], max_retries: int = 3
    ) -> Dict[str, Any]:
        """Generate synthetic data for all variable fields.

        Args:
            template: Classification result with variable_fields
            max_retries: Maximum retry attempts

        Returns:
            Dict mapping field_type to synthetic value

        Raises:
            SynthesisError: If generation fails
        """
        variable_fields = template.get("variable_fields", [])
        if not variable_fields:
            logger.warning("No variable fields to generate data for")
            return {}

        logger.info(f"Starting synthetic data generation for {len(variable_fields)} fields")

        # Extract unique field types
        field_types = list(set(field["fieldType"] for field in variable_fields))
        logger.debug(f"Unique field types to generate: {field_types}")

        # Build relationship constraints
        logger.debug("Building relationship constraints for field types")
        constraint_rules = self._build_constraint_rules(field_types)
        if constraint_rules != "- No specific constraints":
            logger.debug(f"Applying constraints: {constraint_rules}")

        # Construct prompt
        system_prompt = """You are an expert at generating realistic synthetic data for forms and documents.

Generate diverse, realistic data that:
- Is internally consistent (age matches date_of_birth, etc.)
- Uses diverse names, ethnicities, and demographics
- Follows proper formats (phone: (XXX) XXX-XXXX, dates: MM/DD/YYYY)
- Is HIPAA-compliant and realistic
- Maintains logical relationships between fields

Return ONLY valid JSON with no additional text."""

        user_prompt = f"""Generate realistic synthetic data for these field types:
{json.dumps(field_types, indent=2)}

RELATIONSHIP CONSTRAINTS:
{constraint_rules}

Additional constraints:
- If date_of_birth exists, calculate age correctly
- Phone numbers should be valid format: (XXX) XXX-XXXX
- Dates should be MM/DD/YYYY format
- Names should be diverse (various ethnicities, genders)
- Medical record numbers (mrn): use format MRN followed by 8-10 digits
- Addresses should be complete and realistic
- SSN format: XXX-XX-XXXX

Return JSON mapping field_type to value:
{{
  "patient_name": "María García",
  "date_of_birth": "07/15/1975",
  "age": "49",
  "phone_number": "(512) 555-1234",
  "mrn": "MRN87654321",
  "city": "Austin",
  "state": "TX",
  "zip": "78701"
}}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response_content = self.chat_completion(
                messages=messages,
                temperature=self.settings.synthesis_temperature,
                max_tokens=self.settings.max_tokens_synthesis,
                response_format={"type": "json_object"},
                max_retries=max_retries,
            )

            # Parse JSON response
            logger.debug("Parsing synthetic data response from LLM")
            try:
                synthetic_data = json.loads(response_content)
                logger.info(
                    f"Synthetic data generation complete: {len(synthetic_data)} field types generated"
                )
                logger.debug(f"Generated data preview: {list(synthetic_data.items())[:5]}")
                return synthetic_data

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from LLM: {response_content[:200]}")
                raise SynthesisError(f"Invalid JSON response: {e}") from e

        except LLMError as e:
            raise SynthesisError(f"Synthesis failed: {e}") from e

    def _simplify_json_for_classification(
        self, pdf_json: Dict[str, Any]
    ) -> tuple[Dict[str, Any], int]:
        """Simplify PDF JSON for classification (text-only, no coordinates).

        Args:
            pdf_json: Full PDF JSON from Stirling

        Returns:
            Tuple of (simplified JSON with only text and fontSize, count of headers excluded)
        """
        simplified = {"pages": []}
        headers_excluded = 0

        for page in pdf_json.get("pages", []):
            # Note: Stirling PDF uses "pageNumber" (camelCase) in its JSON
            page_number = page.get("pageNumber") or page.get("number") or 1
            page_data = {
                "number": page_number,
                "textElements": [],
            }

            # Include only text and fontSize for each element
            for elem in page.get("textElements", []):
                text = elem.get("text", "").strip()
                if not text:
                    continue

                # Sanitize text: remove control characters and invalid Unicode
                text = self._sanitize_text(text)
                if not text:
                    continue

                font_size = elem.get("fontSize", 12)

                # Skip headers (large text)
                if font_size > HEADER_THRESHOLD:
                    logger.debug(f"Skipping header: '{text}' (fontSize={font_size})")
                    headers_excluded += 1
                    continue

                # Skip placeholders (only dots, underscores, or similar)
                if all(c in "…._-" for c in text):
                    logger.debug(f"Skipping placeholder: '{text}'")
                    continue

                # Skip very short text (unless it's a number)
                if len(text) < 3 and not text.isdigit():
                    logger.debug(f"Skipping short text: '{text}'")
                    continue

                simplified_elem = {
                    "text": text,
                    "fontSize": font_size,
                    "pageNumber": page_number,
                }
                page_data["textElements"].append(simplified_elem)

            simplified["pages"].append(page_data)

        logger.info(
            f"Simplified JSON for classification: "
            f"{sum(len(p['textElements']) for p in simplified['pages'])} elements, "
            f"{headers_excluded} headers excluded"
        )

        return simplified, headers_excluded

    def _sanitize_text(self, text: str) -> str:
        """Remove control characters and invalid Unicode from text.

        Args:
            text: Input text string

        Returns:
            Sanitized text string
        """
        import re

        # Remove control characters (except tab, newline, carriage return)
        # Control characters are in the range \x00-\x1f and \x7f-\x9f
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def _sanitize_json_response(self, json_str: str) -> str:
        """Sanitize JSON response by removing invalid escape sequences.

        Args:
            json_str: JSON string from LLM

        Returns:
            Sanitized JSON string
        """
        import re

        # Remove invalid Unicode escape sequences
        # Valid ones are \uXXXX where X is a hex digit
        # Invalid ones have control characters or non-hex characters
        def replace_invalid_escape(match):
            escape_seq = match.group(0)
            # Check if it's a valid hex escape
            try:
                # Extract the hex part
                hex_part = escape_seq[2:]  # Skip \u
                if len(hex_part) == 4 and all(c in '0123456789abcdefABCDEF' for c in hex_part):
                    # Valid escape, but check if it's a control character
                    code_point = int(hex_part, 16)
                    if code_point < 0x20 or (0x7f <= code_point <= 0x9f):
                        # Control character, remove it
                        return ''
                    return escape_seq
                else:
                    # Invalid escape, remove it
                    return ''
            except:
                return ''

        # Find and replace all \uXXXX sequences
        json_str = re.sub(r'\\u[0-9a-fA-F]{4}', replace_invalid_escape, json_str)

        return json_str

    def _fill_missing_page_numbers(
        self, variable_fields: List[Dict[str, Any]], simplified_json: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Fill in missing pageNumbers by matching text to original input.

        Args:
            variable_fields: Variable fields from LLM (may have null pageNumbers)
            simplified_json: Original simplified JSON sent to LLM

        Returns:
            Variable fields with pageNumbers filled in
        """
        logger.info(f"Post-processing: filling missing pageNumbers for {len(variable_fields)} fields")

        # Build a lookup map: text -> pageNumber
        text_to_page = {}
        for page in simplified_json.get("pages", []):
            page_number = page.get("number")
            for elem in page.get("textElements", []):
                text = elem.get("text", "").strip()
                if text:
                    text_to_page[text] = page_number

        logger.debug(f"Built lookup map with {len(text_to_page)} text entries")

        # Fill in missing pageNumbers
        filled_count = 0
        for field in variable_fields:
            if field.get("pageNumber") is None:
                text = field.get("text", "").strip()
                if text in text_to_page:
                    field["pageNumber"] = text_to_page[text]
                    filled_count += 1
                    logger.debug(f"Filled pageNumber={text_to_page[text]} for text='{text}'")
                else:
                    # Default to 1 if not found
                    field["pageNumber"] = 1
                    filled_count += 1
                    logger.warning(
                        f"Could not find pageNumber for text='{text}', defaulting to 1"
                    )

        logger.info(f"Filled {filled_count} missing pageNumbers")
        return variable_fields

    def _build_constraint_rules(self, field_types: List[str]) -> str:
        """Generate constraint rules for field relationships.

        Args:
            field_types: List of field type strings

        Returns:
            Formatted constraint rules string
        """
        constraints = []

        # Date constraints
        if "date_of_birth" in field_types and "age" in field_types:
            constraints.append("- age must be calculated correctly from date_of_birth")

        if "marriage_date" in field_types and "date_of_birth" in field_types:
            constraints.append(
                "- marriage_date must be at least 18 years after date_of_birth"
            )

        if "start_date" in field_types and "end_date" in field_types:
            constraints.append("- end_date must be after start_date")

        # Name consistency
        if "spouse_name" in field_types and "patient_name" in field_types:
            constraints.append(
                "- spouse_name should be a different person than patient_name"
            )

        # Address consistency
        if (
            "city" in field_types
            and "state" in field_types
            and "zip" in field_types
        ):
            constraints.append(
                "- city, state, and zip must match (e.g., Austin, TX, 78701)"
            )

        return "\n".join(constraints) if constraints else "- No specific constraints"
