**Тіл / Language:** [Русский](../ru/STACK.md) · [English](../en/STACK.md) · [Қазақша](STACK.md)

# Технологиялар стегі (өзектілігі — Aug 2026)

Хакатон және одан әрі масштабтау үшін бекітілген мақсатты нұсқалар.

## Runtime / Infra

| Компонент | Нұсқа | Ескертпе |
|-----------|--------|------------|
| Python | 3.12 | Docker `python:3.12-slim` — тұрақты GIS wheels |
| PostgreSQL + PostGIS | 17 + 3.5 | образ `postgis/postgis:17-3.5` |
| Redis | 8 | `redis:8-alpine` |
| MinIO | latest (dev) | проде — pin digest/tag |
| Node | 22 LTS | frontend Docker |

## Backend

| Компонент | Желі | Мәртебе |
|-----------|-------|--------|
| FastAPI | 0.115+ | өзекті |
| Pydantic | v2 | өзекті |
| SQLAlchemy | 2.x async | өзекті |
| Alembic | 1.13+ | өзекті |
| Celery | 5.x | өзекті |
| GeoAlchemy2 / Shapely / GeoPandas | current | өзекті |
| Playwright / BeautifulSoup / lxml | current | өзекті |
| CatBoost | current | tabular risk SOTA-тәжірибе |
| LLM | OpenAI `gpt-5.6-terra` | explain only |

## Frontend

| Компонент | Нұсқа | Мәртебе |
|-----------|--------|--------|
| React | 19.x | өзекті |
| react-dom | 19.x | өзекті |
| react-leaflet | 5.x | React 19 қажет |
| Leaflet | 1.9.x | өзекті |
| MUI | 7.x | өзекті |
| Vite | 6.x | өзекті (7/8 — опционалды) |
| TypeScript | 5.8+ | өзекті |

## MVP-ге саналы түрде тартпаймыз

- Kafka / K8s / Feast — Phase 2+
- Жергілікті Ollama — LLM API-мен ауыстырылған
- React 18 / MUI 6 / PostGIS 16 — ескірген пиндер ретінде алынған
