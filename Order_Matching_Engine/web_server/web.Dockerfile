FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
COPY web_server/web_server.py /app/web_server.py
COPY web_server/templates /app/templates

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "web_server.py"]
