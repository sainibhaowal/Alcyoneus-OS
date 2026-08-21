# Alcyoneus OS - Production Dockerfile
# Multi-stage build for minimal production image

# Build stage
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./
COPY README.md ./

# Install package in development mode with all extras
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -e ".[google-genai,openai,mcp,pg_checkpoint,redis,kafka,otel]"

# Production stage
FROM python:3.12-slim AS production

# Create non-root user
RUN groupadd -r alcyoneus && useradd -r -g alcyoneus -d /app -s /sbin/nologin alcyoneus

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=alcyoneus:alcyoneus alcyoneus/ ./alcyoneus/
COPY --chown=alcyoneus:alcyoneus examples/ ./examples/

# Create directories for data
RUN mkdir -p /app/data /app/logs /app/checkpoints && \
    chown -R alcyoneus:alcyoneus /app

# Switch to non-root user
USER alcyoneus

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ALCYONEUS_CONFIG=/app/config.yaml \
    ALCYONEUS_LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose ports
EXPOSE 8000 9090

# Default command
CMD ["python", "-m", "alcyoneus.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]