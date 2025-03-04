FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    tcpdump \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first to leverage Docker cache
WORKDIR /deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set up application
WORKDIR /app
COPY server/server.py .

CMD ["python", "server.py"]