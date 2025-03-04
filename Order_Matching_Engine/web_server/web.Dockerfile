FROM python:3.9-slim

# Install Python dependencies first to leverage Docker cache
WORKDIR /deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir Flask-Session

# Set up application
WORKDIR /app
COPY web_server/web_server.py .
COPY web_server/templates templates/

# Create sessions directory
RUN mkdir -p /tmp/flask_sessions && \
    chmod 777 /tmp/flask_sessions

CMD ["python", "web_server.py"]
