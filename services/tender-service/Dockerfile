FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgeos-c1v5 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    fastapi uvicorn pydantic \
    "sqlalchemy[asyncio]>=2.0" asyncpg alembic geoalchemy2 greenlet
COPY packages/shared /packages/shared
RUN pip install -e /packages/shared
COPY services/tender-service/alembic.ini ./alembic.ini
COPY services/tender-service/alembic ./alembic
COPY services/tender-service/app ./app
COPY services/tender-service/entrypoint.sh ./entrypoint.sh
COPY data/fixtures /data/fixtures
RUN chmod +x /app/entrypoint.sh
ENV PYTHONPATH=/app
EXPOSE 8001
CMD ["/app/entrypoint.sh"]
