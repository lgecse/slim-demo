FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy source code and dependencies
COPY pyproject.toml .
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir -e .

# Support for environment variables (especially OPENAI_API_KEY)
ENV PYTHONPATH=/app

# Note: objects.txt no longer needed - using LLM for object generation

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash gameuser && \
    chown -R gameuser:gameuser /app
USER gameuser

# Default command (will be overridden in Kubernetes)
CMD ["guessing-game", "--help"]
