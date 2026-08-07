**Language:** [Русский](../ru/STACK.md) · [English](STACK.md) · [Қазақша](../kk/STACK.md)

# Technology Stack (current as of Aug 2026)

Pinned target versions for the hackathon and further scaling.

## Runtime / Infra

| Component | Version | Note |
|-----------|---------|------|
| Python | 3.12 | Docker `python:3.12-slim` — stable GIS wheels |
| PostgreSQL + PostGIS | 17 + 3.5 | image `postgis/postgis:17-3.5` |
| Redis | 8 | `redis:8-alpine` |
| MinIO | latest (dev) | in prod — pin digest/tag |
| Node | 22 LTS | frontend Docker |

## Backend

| Component | Line | Status |
|-----------|------|--------|
| FastAPI | 0.115+ | current |
| Pydantic | v2 | current |
| SQLAlchemy | 2.x async | current |
| Alembic | 1.13+ | current |
| Celery | 5.x | current |
| GeoAlchemy2 / Shapely / GeoPandas | current | current |
| Playwright / BeautifulSoup / lxml | current | current |
| CatBoost | current | tabular risk SOTA practice |
| LLM | OpenAI `gpt-5.6-terra` | explain only |

## Frontend

| Component | Version | Status |
|-----------|---------|--------|
| React | 19.x | current |
| react-dom | 19.x | current |
| react-leaflet | 5.x | requires React 19 |
| Leaflet | 1.9.x | current |
| MUI | 7.x | current |
| Vite | 6.x | current (7/8 — optional) |
| TypeScript | 5.8+ | current |

## Consciously Not Pulling into MVP

- Kafka / K8s / Feast — Phase 2+
- Local Ollama — replaced by LLM API
- React 18 / MUI 6 / PostGIS 16 — dropped as outdated pins
