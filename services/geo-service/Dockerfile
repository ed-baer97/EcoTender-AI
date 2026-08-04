FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic
COPY services/geo-service/app ./app
COPY data/fixtures /data/fixtures
ENV PYTHONPATH=/app
EXPOSE 8003
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
