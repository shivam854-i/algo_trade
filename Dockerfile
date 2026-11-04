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

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy codebase
COPY . .

# Create cache and alert log directories
RUN mkdir -p data/cache data/alerts

# Expose ports: 8000 for FastAPI REST backend, 8501 for Streamlit UI
EXPOSE 8000
EXPOSE 8501

# Default command: launch FastAPI high-performance SaaS API
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
