# Stirling PDF SDG - Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    ghostscript \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN pip install uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package
RUN uv pip install --system -e .

# Copy test scripts
COPY test_extraction.py full_pipeline.py ./

# Create directories for data
RUN mkdir -p /data/input /data/output /data/cache

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Default command
CMD ["python", "-c", "from stirling_sdg import LocalStirlingClient; print('Stirling PDF SDG ready!')"]
