FROM python:3.9-slim

WORKDIR /app

# Install system dependencies first to leverage caching
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && \
    apt-get install -y \
    tcpdump \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories with proper permissions
RUN mkdir -p /app/qlogs /app/certs && \
    chmod 777 /app/qlogs /app/certs

# Install Python dependencies first to leverage caching
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# Copy application code last since it changes most frequently
COPY client.py .

# Set the entrypoint to ensure proper working directory
WORKDIR /app
CMD ["python", "client.py"]