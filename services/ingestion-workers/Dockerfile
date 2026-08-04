FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "celery[redis]" redis pydantic httpx
COPY packages/shared /packages/shared
RUN pip install -e /packages/shared
COPY data/fixtures /data/fixtures
COPY services/ingestion-workers/app ./app
ENV PYTHONPATH=/app
CMD ["celery", "-A", "app.workers.celery_app", "worker", "-l", "INFO", "-Q", "ingest,default"]
