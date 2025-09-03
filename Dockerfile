FROM python:3.10-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1 \
PIP_NO_CACHE_DIR=1 \
PORT=8000
WORKDIR /app
# System deps (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
build-essential curl \
&& rm -rf /var/lib/apt/lists/*


# Install Python deps first for better caching
COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt


# Run as non-root
RUN useradd -m appuser
USER appuser


# Copy app source
COPY ./ ./


# Gunicorn defaults; override via App Settings if needed
ENV GUNICORN_CMD_ARGS="--bind=0.0.0.0:${PORT} --workers=2 --threads=8 --timeout=120 --access-logfile=- --error-logfile=-"
EXPOSE 8000


# Start the app
CMD ["gunicorn", "app:app"]