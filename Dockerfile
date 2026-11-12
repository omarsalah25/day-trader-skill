# ==============================================================================
# Day Trader 24/7 - Autonomous Market Terminal & Trading Engine
# Multi-arch production Docker image (linux/amd64, linux/arm64)
# ==============================================================================
FROM python:3.11-slim-bookworm

# Metadata
LABEL maintainer="Day Trader 24/7 Team"
LABEL description="Autonomous 24/7 Day Trader engine and real-time dashboard for chart scanning, news monitoring, bar-by-bar entry timing, Monte Carlo simulations, and risk management."

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    TZ=America/New_York \
    DEBIAN_FRONTEND=noninteractive

# Install curl, ca-certificates, and tzdata for healthchecks, timezones, and secure SSL/TLS
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user
RUN groupadd -g 1000 trader && \
    useradd -u 1000 -g trader -m -s /bin/bash trader

# Set working directory
WORKDIR /app

# Copy application directories and files
COPY --chown=trader:trader app/ ./app/
COPY --chown=trader:trader web/ ./web/
COPY --chown=trader:trader trader/ ./trader/
COPY --chown=trader:trader trader-alerts/ ./trader-alerts/
COPY --chown=trader:trader trader-analyst/ ./trader-analyst/
COPY --chown=trader:trader trader-broker/ ./trader-broker/
COPY --chown=trader:trader trader-budget/ ./trader-budget/
COPY --chown=trader:trader trader-entry/ ./trader-entry/
COPY --chown=trader:trader trader-exit/ ./trader-exit/
COPY --chown=trader:trader trader-news/ ./trader-news/
COPY --chown=trader:trader trader-pelosi/ ./trader-pelosi/
COPY --chown=trader:trader trader-risk/ ./trader-risk/
COPY --chown=trader:trader trader-scanner/ ./trader-scanner/
COPY --chown=trader:trader trader-timemachine/ ./trader-timemachine/
COPY --chown=trader:trader tests/ ./tests/
COPY --chown=trader:trader start_app.sh ./start_app.sh

# Ensure script is executable and permissions are set
RUN chmod +x start_app.sh && \
    chown -R trader:trader /app

# Switch to non-root user for security
USER trader

# Expose web application port
EXPOSE 8080

# Define volume for persistent portfolio and state data
VOLUME ["/app/trader"]

# Healthcheck to verify the HTTP server and 24/7 background engine
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/api/status || exit 1

# Start server entrypoint
ENTRYPOINT ["python3", "app/server.py"]
CMD ["--port", "8080"]
