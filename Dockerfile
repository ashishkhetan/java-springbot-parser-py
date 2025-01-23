FROM python:3.8-slim

# Install git and graphviz
RUN apt-get update && \
    apt-get install -y git graphviz && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY analyze.py .
COPY neo4j_store.py .
COPY process_repositories.py .

# Run the repository processor
CMD ["python", "process_repositories.py"]
