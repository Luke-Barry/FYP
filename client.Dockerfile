FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
COPY client.py .

RUN apt-get update && \
    apt-get install -y \
    tcpdump \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

CMD ["python", "client.py"]