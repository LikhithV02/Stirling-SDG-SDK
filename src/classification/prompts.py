"""Prompt templates for LLM classification and synthesis."""

# Classification system prompt
CLASSIFICATION_SYSTEM = """You are an expert at analyzing document structures and identifying variable vs static content.

Variable elements are data that changes per document instance:
- Names, dates, addresses, phone numbers, email addresses
- Medical record numbers, SSN, ID numbers
- Checkbox values, measurements, amounts, quantities
- Handwritten or typed patient/user data
- Form field values

Static elements are fixed content:
- Form labels, field names
- Instructions, legal text, disclaimers
- Headers, footers, page numbers
- Form structure and layout text

Return ONLY valid JSON with no additional text."""

# Classification user prompt template
CLASSIFICATION_USER_TEMPLATE = """Analyze this PDF JSON structure and identify VARIABLE text elements.

JSON structure (simplified):
{pdf_json}

Return JSON in this exact format:
{{
  "variable_elements": [
    {{
      "pageNumber": 1,
      "text": "John Smith",
      "fieldType": "patient_name",
      "confidence": 0.95,
      "reasoning": "Person's name following 'Patient Name:' label"
    }}
  ]
}}

Field types should be descriptive lowercase_with_underscores (e.g., patient_name, date_of_birth, phone_number, address, etc.)."""

# Synthesis system prompt
SYNTHESIS_SYSTEM = """You are an expert at generating realistic synthetic data for forms and documents.

Generate diverse, realistic data that:
- Is internally consistent (age matches date_of_birth, etc.)
- Uses diverse names, ethnicities, and demographics
- Follows proper formats (phone: (XXX) XXX-XXXX, dates: MM/DD/YYYY)
- Is HIPAA-compliant and realistic
- Maintains logical relationships between fields

Return ONLY valid JSON with no additional text."""

# Synthesis user prompt template
SYNTHESIS_USER_TEMPLATE = """Generate realistic synthetic data for these field types:
{field_types}

Constraints:
- If date_of_birth exists, calculate age correctly
- Phone numbers should be valid format: (XXX) XXX-XXXX
- Dates should be MM/DD/YYYY format
- Names should be diverse (various ethnicities, genders)
- Medical record numbers (mrn): use format MRN followed by 8-10 digits
- Addresses should be complete and realistic

Return JSON mapping field_type to value:
{{
  "patient_name": "María García",
  "date_of_birth": "07/15/1975",
  "age": "48",
  "phone_number": "(555) 123-4567",
  "mrn": "MRN87654321",
  "address": "123 Main St, Anytown, CA 90210"
}}"""
