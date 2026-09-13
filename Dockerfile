# Single-lineage Dockerfile for Petrosa Realtime Strategies
# Optimized for production deployment with security and performance
#
# NOTE (petrosa_k8s#195/petrosa-realtime-strategies#195 AC7): this used to carry two
# divergent lineages (python:3.11-slim and python:3.11-alpine, 7 stages) but CI built with
# no --target so only the last stage (alpine-production) was ever actually built/deployed.
# Verified live in the pod 2026-09-11 (Alpine, opentelemetry-instrument present, UID 1000
# via pod securityContext) that the alpine lineage is what runs in production. The slim
# lineage (builder/production/development/testing/optimized) was dead weight and has been
# removed; this is the alpine lineage, renamed to the canonical stage names.

# Build stage
FROM python:3.11-alpine AS builder

# Build arguments
ARG VERSION=dev
ARG COMMIT_SHA=unknown
ARG BUILD_DATE=unknown

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install requirements
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Final production stage
FROM python:3.11-alpine AS production

# Build arguments
ARG VERSION=dev
ARG COMMIT_SHA=unknown
ARG BUILD_DATE=unknown

# Metadata labels
LABEL org.opencontainers.image.title="Petrosa Realtime Strategies" \
      org.opencontainers.image.description="Lightweight stateless trading signal service" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${COMMIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_VERSION="${VERSION}"

# Install runtime dependencies
RUN apk add --no-cache \
    curl \
    ca-certificates

# Create non-root user
RUN addgroup -S appuser && adduser -S appuser -G appuser

# Copy virtual environment
COPY --from=builder /opt/venv /opt/venv

# Create and set working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser . .

# Create directories and set permissions
RUN mkdir -p logs tmp && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

# Expose health check port
EXPOSE 8080

# Default command
CMD ["python", "-m", "strategies.main", "run"]
