# Use Python base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY app ./app
COPY run.py .

# Expose port
EXPOSE 8000

# Run the FastAPI application
CMD ["python", "run.py"] 