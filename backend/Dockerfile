# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt constraints.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

# Copy application code into ask_forge/backend so the `ask_forge.backend.app...` imports resolve
COPY . ./ask_forge/backend/
RUN touch ask_forge/__init__.py

# Create necessary directories
RUN mkdir -p data/user_db .chroma

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "ask_forge.backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]