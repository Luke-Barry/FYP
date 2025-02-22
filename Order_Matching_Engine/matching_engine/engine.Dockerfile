FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
COPY matching_engine/engine.py /app/engine.py

RUN apt-get update && \
    apt-get install -y \
    tcpdump \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

CMD ["python", "engine.py"]