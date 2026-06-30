# =============================================================================
# X Stealth AutoPoster - Production Dockerfile (Best Practices 2026)
# =============================================================================
FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy AS base

# Security: Create non-root user
RUN groupadd -r botuser && useradd -r -g botuser botuser

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only)
RUN playwright install --with-deps chromium

# Create necessary directories with correct permissions
RUN mkdir -p logs screenshots traces data && \
    chown -R botuser:botuser /app

# Copy application code
COPY --chown=botuser:botuser src/ ./src/
COPY --chown=botuser:botuser data/ ./data/

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO

# Switch to non-root user
USER botuser

# Healthcheck (simple - checks if Python can import main modules)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import src.logging_config; print('healthy')" || exit 1

# Default command
CMD ["python", "-m", "src.main"]
