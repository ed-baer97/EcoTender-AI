FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "celery[redis]" \
    redis \
    pydantic \
    httpx \
    "playwright>=1.40" \
    "beautifulsoup4>=4.12" \
    "lxml>=5" \
    "pypdf>=4.0" \
    "python-docx>=1.1" \
    "minio>=7.2"

RUN playwright install --with-deps chromium

COPY packages/shared /packages/shared
RUN pip install -e /packages/shared
COPY data/fixtures /data/fixtures
COPY services/ingestion-workers/app ./app
ENV PYTHONPATH=/app
CMD ["celery", "-A", "app.workers.celery_app", "worker", "-l", "INFO", "-Q", "ingest,default"]
