# EcoTender AI

Интеллектуальная платформа анализа экологических тендеров Каспийского моря  
**Caspian Hackathon 2026**

> Принцип проектирования: MVP за 48 часов без «игрушечной» архитектуры.  
> Тот же каркас масштабируется до государственной платформы (multi-country, audit, RBAC, event bus).

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d --build
python scripts/smoke_check.py
```
| Сервис        | URL                    |
|---------------|------------------------|
| Web UI        | http://localhost:5173  |
| API Gateway   | http://localhost:8000  |
| API Docs      | http://localhost:8000/docs |
| Flower        | http://localhost:5555  |
| MinIO         | http://localhost:9101  |

**Ключи API** — через кабинет администратора (без правки `.env` и recreate):  
войти как `admin@ecotender.kz` / `admin123` → **Кабинет администратора** → LLM / парсеры.  
At rest ключи шифруются Fernet (`SECRET_ENCRYPTION_KEY` / fallback `JWT_SECRET`), в Redis/file — префикс `enc:v1:`.

## Документация

| Документ | Содержание |
|----------|------------|
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | Питч 2 минуты — что кликать |
| [docs/GOSZAKUP_PARSER.md](docs/GOSZAKUP_PARSER.md) | Живой парсер goszakup OWS v3 |
| [docs/STACK.md](docs/STACK.md) | Актуальные версии стека (Aug 2026) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Полная архитектура, микросервисы, масштабирование |
| [docs/ER_DIAGRAM.md](docs/ER_DIAGRAM.md) | ER-модель PostgreSQL/PostGIS |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Открытые источники данных Каспия |
| [docs/ML_RISK_ENGINE.md](docs/ML_RISK_ENGINE.md) | CatBoost + LLM, признаки, обучение |
| [docs/API.md](docs/API.md) | REST API контракты |
| [docs/MVP_48H.md](docs/MVP_48H.md) | Roadmap 48ч, задачи по ролям |
| [docs/SCALING.md](docs/SCALING.md) | Путь к гос. платформе |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Фазы 1→3: polish → secrets → platform |

## Стек

**Backend:** FastAPI · SQLAlchemy 2 · Alembic · Celery · Redis 8 · PostgreSQL 17 + PostGIS 3.5  
**Frontend:** React 19 · TypeScript · Vite 6 · MUI 7 · Leaflet / react-leaflet 5  
**Ingestion:** Playwright · BeautifulSoup · lxml  
**AI:** CatBoost (свой score) + LLM API gpt-5.6-terra (объяснение) · template fallback без ключа  
**GIS:** PostGIS 3.5 · GeoPandas · Shapely · Leaflet

## Структура монорепо

```
apps/web                 # React SPA
services/
  api-gateway            # BFF / auth / rate-limit
  tender-service         # тендеры, контракты, участники
  market-service         # рыночные цены
  geo-service            # PostGIS, слои, снимки
  risk-engine            # CatBoost + anomaly + LLM API explain
  ingestion-workers      # парсеры + Celery
packages/shared          # pydantic schemas, events, enums
ml/                      # обучение, feature store stubs, models/
infra/                   # nginx, otel, init SQL
docs/
```

## Лицензия

MIT — хакатон / open source demo. Для продакшена гос. контура — отдельное соглашение.
