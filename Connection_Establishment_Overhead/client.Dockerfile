FROM python:3.9-slim

RUN pip install aioquic
WORKDIR /app

COPY client.py /app/client.py
CMD ["python", "client.py"]
