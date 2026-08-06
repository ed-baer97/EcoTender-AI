FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic httpx catboost pandas redis \
    "pypdf>=4.0" "python-docx>=1.1" "beautifulsoup4>=4.12" "lxml>=5" "minio>=7.2"
COPY packages/shared /packages/shared
RUN pip install -e /packages/shared
COPY services/risk-engine/app ./app
ENV PYTHONPATH=/app
EXPOSE 8004
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
