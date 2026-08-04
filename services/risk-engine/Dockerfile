FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic httpx catboost pandas
COPY packages/shared /packages/shared
RUN pip install -e /packages/shared
COPY services/risk-engine/app ./app
ENV PYTHONPATH=/app
EXPOSE 8004
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
