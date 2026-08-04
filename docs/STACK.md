# Стек технологий (актуальность — Aug 2026)

Зафиксированные целевые версии для хакатона и дальнейшего масштабирования.

## Runtime / Infra

| Компонент | Версия | Примечание |
|-----------|--------|------------|
| Python | 3.12 | Docker `python:3.12-slim` — стабильные GIS wheels |
| PostgreSQL + PostGIS | 17 + 3.5 | образ `postgis/postgis:17-3.5` |
| Redis | 8 | `redis:8-alpine` |
| MinIO | latest (dev) | в проде — pin digest/tag |
| Node | 22 LTS | frontend Docker |

## Backend

| Компонент | Линия | Статус |
|-----------|-------|--------|
| FastAPI | 0.115+ | актуально |
| Pydantic | v2 | актуально |
| SQLAlchemy | 2.x async | актуально |
| Alembic | 1.13+ | актуально |
| Celery | 5.x | актуально |
| GeoAlchemy2 / Shapely / GeoPandas | current | актуально |
| Playwright / BeautifulSoup / lxml | current | актуально |
| CatBoost | current | tabular risk SOTA-практика |
| LLM | OpenAI `gpt-5.6-terra` | explain only |

## Frontend

| Компонент | Версия | Статус |
|-----------|--------|--------|
| React | 19.x | актуально |
| react-dom | 19.x | актуально |
| react-leaflet | 5.x | требует React 19 |
| Leaflet | 1.9.x | актуально |
| MUI | 7.x | актуально |
| Vite | 6.x | актуально (7/8 — опционально) |
| TypeScript | 5.8+ | актуально |

## Сознательно не тянем в MVP

- Kafka / K8s / Feast — Phase 2+
- Локальный Ollama — заменён LLM API
- React 18 / MUI 6 / PostGIS 16 — сняты как устаревшие пины
