# Multi-Asset Quantitative Market Prediction Engine (Project SYNAPSE-TITAN)
# High-performance Linux container for cloud deployment (AWS ECS, GCP Cloud Run, Azure, Kubernetes)

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build-essential for compiling C/C++ quant extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged non-root user
RUN groupadd -r titan && useradd -r -g titan -d /app -s /sbin/nologin titan

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy codebase
COPY . .

# Create cache and alert log directories and assign ownership
RUN mkdir -p data/cache data/alerts && chown -R titan:titan /app

# Expose port 8000 for FastAPI REST backend and React Trading Terminal
EXPOSE 8000

# Run container as non-root user
USER titan

# Default command: launch FastAPI high-performance SaaS API and React terminal
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
