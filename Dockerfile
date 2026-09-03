FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for building and database connection
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies directly with complete dependency tree
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src /app/src
COPY dashboard /app/dashboard
COPY architecture_graph.html /app/architecture_graph.html

# Create non-root user for security
RUN useradd -m -s /bin/bash agent && \
    chown -R agent:agent /app

USER agent

# Expose standard port
EXPOSE 8000

# Run the application with dynamic port support
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
