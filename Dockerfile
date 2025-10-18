# Base image
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg

# Set working directory
WORKDIR /app

# Copy requirements.txt and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 5000

# Run Flask application
#CMD ["python", "app.py"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
