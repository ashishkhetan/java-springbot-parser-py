# Use Python 3.11 as base image
FROM python:3.11-slim

# Install system dependencies including Graphviz
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p repos graphs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the processor
CMD ["python", "process_repositories.py"]
