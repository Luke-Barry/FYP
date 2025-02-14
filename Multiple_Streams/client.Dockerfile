FROM python:3.10

WORKDIR /app
COPY . /app

RUN pip install aioquic

# Ensure directories exist for qlogs and certificates
RUN mkdir -p /app/qlogs && mkdir -p /app/certs

CMD ["python", "client.py"]
