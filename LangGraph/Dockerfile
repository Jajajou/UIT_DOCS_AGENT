# LangGraph Agent Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    poppler-utils \
    libmupdf-dev \
    mupdf-tools \
    tesseract-ocr \
    tesseract-ocr-vie \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements_v3.txt ./requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "langgraph-cli[inmem]>=0.2.8" uvicorn pymupdf pytesseract pillow requests addict lightrag-hku langchain langchain-community

# Copy application code
COPY src ./src
COPY langgraph.json ./langgraph.json

# Set environment variables
ENV PYTHONPATH=/app:/app/src
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8123

# Run the LangGraph API
CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "8123"]
