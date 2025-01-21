# Use Python base image
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y gcc python3-dev libxml2-dev libxslt-dev libffi-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy environment variables
COPY .env .

# Copy application code
COPY app ./app
COPY run.py .

# Expose port
EXPOSE 8000

# Run the FastAPI application
CMD ["python", "run.py"] 