# EcoTender AI

**Language:** [Русский](README.ru.md) · [English](README.en.md) · [Қазақша](README.kk.md)

AI platform for transparency of environmental tenders around the Caspian Sea  
**Caspian Hackathon 2026** · Caspian Sea Action Week

> AI + GIS + open procurement: Risk Score for eco-tenders for government, auditors, and public oversight.  
> Docker Compose MVP; designed to scale into a national platform.

**GitHub:** https://github.com/ed-baer97/EcoTender-AI  
**Team:** IT LYCEUM Team · [AUTHORS.md](AUTHORS.md)  
**Project description:** [docs/en/PROJECT_DESCRIPTION.md](docs/en/PROJECT_DESCRIPTION.md)  
**Documentation index:** [docs/README.md](docs/README.md)

---

## Overview

EcoTender AI collects environmentally relevant public procurement (Kazakhstan / Caspian), compares prices to market references, shows objects on a map (PostGIS + Leaflet), and computes a **Risk Score 0–100** with our own CatBoost model. On top of the score is an explanation layer for auditors: an OpenAI-compatible API (cloud or local on-prem) or a template fallback without a key.

Focus: transparency of funds for Caspian Sea conservation + geospatial monitoring of eco-projects. Risk Score is an analytical signal for review — not a guarantee of outcomes and not a legal accusation.

## Main features

1. **Eco-tender catalog** — list, filters, tender card (fixtures / goszakup).
2. **Risk map** — markers by risk band, protected areas / NASA GIBS (demo).
3. **Risk Score** — CatBoost 0–100, bands low → critical; persisted and rescored when parse data changes (or manually).
4. **Explain** — turns the score into auditor language (OpenAI-compatible API / template fallback).
5. **Market comparison** — price deviation from reference.
6. **Ingestion** — goszakup API first (OWS v3), Playwright fallback; Celery + Flower.
7. **People's Patrol** — guest comments and photos on a tender (public oversight).
8. **Admin cabinet** — LLM/parser keys encrypted at rest.
9. **Auth (demo)** — JWT, roles viewer / analyst / admin.

Details: [docs/en/PROJECT_DESCRIPTION.md](docs/en/PROJECT_DESCRIPTION.md).

---

## Minimum system requirements

| Resource | Minimum |
|----------|---------|
| OS | Windows 10/11, macOS 12+, Linux (x86_64) |
| CPU / RAM | 4 vCPU · **8 GB RAM** (16 GB recommended) |
| Disk | ~10 GB free (Docker images) |
| Network | For image builds; offline demo works on fixtures |

## Required software

- [Docker](https://docs.docker.com/get-docker/) **24+** and Docker Compose v2  
- (Optional) Python **3.11+** — only for host `scripts/smoke_check.py`  
- (Optional) Git — clone the repository  
- Browser: current Chrome / Edge / Firefox  

LLM key is **optional** (template explain works without it). goszakup OWS token is optional (Playwright stub + fixtures available).

---

## Install

```bash
git clone https://github.com/ed-baer97/EcoTender-AI.git
cd EcoTender-AI
cp .env.example .env
```

Edit `.env` if needed (Postgres/MinIO passwords, `JWT_SECRET`). Demo works with example values.

## Run

```bash
docker compose up -d --build
```

Wait until containers are healthy (first run may take several minutes).

Verify:

```bash
python scripts/smoke_check.py
```

Expected: `SMOKE OK`.

| Service | URL |
|---------|-----|
| Web UI | http://localhost:5173 |
| API Gateway | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Flower (Celery) | http://localhost:5555 |
| MinIO Console | http://localhost:9101 |

Stop: `docker compose down`.

## Test accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@ecotender.kz` | `admin123` |
| Analyst | `analyst@ecotender.kz` | `analyst123` |

LLM/parser keys: sign in as admin → **Admin cabinet**.  
Keys at rest use Fernet (`SECRET_ENCRYPTION_KEY` / fallback `JWT_SECRET`), Redis/file prefix `enc:v1:`.

---

## Project structure

```
apps/web                 # React SPA — map, catalog, admin
services/
  api-gateway            # BFF / auth / rate-limit
  tender-service         # tenders, contracts, participants
  market-service         # market prices
  geo-service            # PostGIS, layers, imagery
  risk-engine            # CatBoost + anomaly + LLM explain
  ingestion-workers      # parsers + Celery
packages/shared          # pydantic schemas, SourceAdapter, secrets
ml/                      # CatBoost training, models/
data/fixtures            # demo tenders and HTML fixtures
infra/                   # postgres init, nginx/otel stubs
docs/ru|en|kk            # documentation in 3 languages
scripts/                 # smoke_check and utilities
```

Architecture: [docs/en/ARCHITECTURE.md](docs/en/ARCHITECTURE.md).

---

## Stack

**Backend:** FastAPI · SQLAlchemy 2 · Alembic · Celery · Redis 8 · PostgreSQL 17 + PostGIS 3.5  
**Frontend:** React 19 · TypeScript · Vite 6 · MUI 7 · Leaflet / react-leaflet 5  
**Ingestion:** Playwright · BeautifulSoup · lxml  
**AI:** CatBoost (own Risk Score) + LLM explain via OpenAI-compatible API (cloud or on-prem; e.g. Qwen / DeepSeek) · template fallback  
**GIS:** PostGIS 3.5 · GeoPandas · Shapely · Leaflet  

Versions: [docs/en/STACK.md](docs/en/STACK.md).

## Documentation

| Document | RU | EN | KK |
|----------|----|----|-----|
| Project description | [ru](docs/ru/PROJECT_DESCRIPTION.md) | [en](docs/en/PROJECT_DESCRIPTION.md) | [kk](docs/kk/PROJECT_DESCRIPTION.md) |
| Architecture | [ru](docs/ru/ARCHITECTURE.md) | [en](docs/en/ARCHITECTURE.md) | [kk](docs/kk/ARCHITECTURE.md) |
| API | [ru](docs/ru/API.md) | [en](docs/en/API.md) | [kk](docs/kk/API.md) |
| Risk Engine | [ru](docs/ru/ML_RISK_ENGINE.md) | [en](docs/en/ML_RISK_ENGINE.md) | [kk](docs/kk/ML_RISK_ENGINE.md) |
| Data sources | [ru](docs/ru/DATA_SOURCES.md) | [en](docs/en/DATA_SOURCES.md) | [kk](docs/kk/DATA_SOURCES.md) |
| ER model | [ru](docs/ru/ER_DIAGRAM.md) | [en](docs/en/ER_DIAGRAM.md) | [kk](docs/kk/ER_DIAGRAM.md) |
| goszakup | [ru](docs/ru/GOSZAKUP_PARSER.md) | [en](docs/en/GOSZAKUP_PARSER.md) | [kk](docs/kk/GOSZAKUP_PARSER.md) |
| Stack | [ru](docs/ru/STACK.md) | [en](docs/en/STACK.md) | [kk](docs/kk/STACK.md) |
| Scaling | [ru](docs/ru/SCALING.md) | [en](docs/en/SCALING.md) | [kk](docs/kk/SCALING.md) |

## License

MIT — hackathon / open source demo. Production government deployment requires a separate agreement.

Open-source libraries and public APIs are used under their respective licenses. Risk Score is an analytical signal, not a legal accusation.
