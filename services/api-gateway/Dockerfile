FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn httpx pydantic celery[redis] redis
COPY packages/shared /packages/shared
RUN pip install -e /packages/shared
COPY services/api-gateway/app ./app
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
