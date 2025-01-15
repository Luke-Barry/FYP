FROM python:3.9-slim

RUN pip install aioquic
WORKDIR /app

COPY server.py /app/server.py
CMD ["python", "server.py"]
