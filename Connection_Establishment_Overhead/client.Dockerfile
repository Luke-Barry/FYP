FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies first to leverage caching
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tcpdump \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories with proper permissions
RUN mkdir -p /app/qlogs /app/certs && \
    chmod 777 /app/qlogs /app/certs

# Install Python dependencies first to leverage caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code last since it changes most frequently
COPY client.py .

# Set the entrypoint to ensure proper working directory
CMD ["python", "client.py"]
