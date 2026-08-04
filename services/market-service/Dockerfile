FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic
COPY services/market-service/app ./app
COPY data/fixtures /data/fixtures
ENV PYTHONPATH=/app
EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
