
# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port 8000
EXPOSE 8000

# Health check to ensure zero-downtime deployment (prevents 502/CORS errors during boot)
HEALTHCHECK --interval=5s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Best-effort database readiness for staging; the API must still boot if DB setup fails.
CMD ["sh", "-c", "(alembic upgrade head && PYTHONPATH=. python scripts/bootstrap_identity.py) || echo 'WARNING: database migration/bootstrap failed'; uvicorn app.main:app --host 0.0.0.0 --port 8000"]
