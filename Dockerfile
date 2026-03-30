# Dockerfile for alertOffice
# Flask web application for CUCM phone group management and FreeSWITCH monitoring

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set Python path to include app directory
ENV PYTHONPATH=/app:$PYTHONPATH

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for data, logs, and recordings
RUN mkdir -p /app/data /app/logs /recordings /logs

# Expose Flask port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/').read()" || exit 1

# Run the application via the startup script
CMD ["sh", "docker-start.sh"]
