# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install FFmpeg and DejaVu/Liberation fonts for 9:16 video rendering and subtitle burning
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-liberation \
    espeak-ng \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/backend/requirements.txt

COPY . /app/backend

RUN mkdir -p /app/generated

EXPOSE 8000

CMD ["sh", "-c", "python -c 'from app.database.migrate import migrate_database; migrate_database()' && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
