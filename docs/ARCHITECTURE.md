# EcoTender AI — Архитектура платформы

## 1. Проектный принцип: «Production-shaped MVP»

Мы **не** строим демо на одном FastAPI + SQLite.  
Мы строим **тонкий срез production-архитектуры**:

| Принцип | Реализация в MVP (48ч) | Масштаб после хакатона |
|---------|------------------------|------------------------|
| Bounded contexts | Отдельные сервисы с чёткими API | Независимое деплой/scaling |
| Адаптеры источников | `SourceAdapter` interface + 1–2 страны | Плагины KZ/AZ/RU/TM/IR |
| События | Redis Streams (outbox) | Kafka / NATS JetStream |
| Идемпотентность | `external_id` + upsert | Exactly-once ingestion |
| Аудит | `audit_log` table + middleware | SIEM / WORM storage |
| Auth | JWT + roles (viewer/analyst/admin) | SSO (Keycloak / ЕСИА / eGov) |
| Observability | structured JSON logs + health | OpenTelemetry + Prometheus |
| Feature flags | env + DB flags | LaunchDarkly / Unleash |
| GIS | PostGIS + tile layers | Vector tiles (Martin/pg_tileserv) |
| AI | CatBoost + LLM API (OpenAI-compatible) | Private LLM / VPC endpoint |

**Правило:** любой хакатонный shortcut должен быть **заменяемым адаптером**, а не жёстко вшитым в доменную логику.

---

## 2. Контекстная карта (C4 Level 1)

```mermaid
flowchart TB
  subgraph Actors
    Analyst[Аналитик / аудитор]
    Public[Публичный наблюдатель]
    Admin[Администратор платформы]
  end

  subgraph EcoTender["EcoTender AI Platform"]
    Web[Web SPA]
    GW[API Gateway]
    Core[Domain Services]
    AI[Risk Engine]
    GIS[Geo Service]
    Ingest[Ingestion Workers]
  end

  subgraph External
    GZ[Госзакупки порталы]
    Market[Рыночные каталоги]
    Sat[Спутниковые API]
    EcoDB[Эко-реестры]
    OSM[OSM / береговая линия]
  end

  Analyst --> Web
  Public --> Web
  Admin --> Web
  Web --> GW
  GW --> Core
  GW --> AI
  GW --> GIS
  Ingest --> GZ
  Ingest --> Market
  Ingest --> Sat
  Ingest --> EcoDB
  Ingest --> OSM
  Ingest --> Core
  Core --> AI
  AI --> GIS
```

---

## 3. Микросервисы (C4 Level 2)

```mermaid
flowchart LR
  Client[React SPA] --> GW[api-gateway :8000]

  GW --> TS[tender-service :8001]
  GW --> MS[market-service :8002]
  GW --> GS[geo-service :8003]
  GW --> RE[risk-engine :8004]

  IW[ingestion-workers] --> Redis[(Redis)]
  IW --> PG[(PostgreSQL+PostGIS)]
  TS --> PG
  MS --> PG
  GS --> PG
  RE --> PG
  RE --> Redis
  RE --> LLMAPI[LLM API OpenAI-compatible]
  IW --> MinIO[(MinIO)]
  GS --> MinIO

  Redis --> CeleryW[Celery Workers]
  CeleryW --> IW
  CeleryW --> RE
```

> **AI split:** CatBoost artifact lives in `risk-engine` (own decision).  
> Explanation goes through external `LLM_BASE_URL` + `LLM_API_KEY`.  
> Without a key → deterministic `template_fallback` (demo-safe offline).
### 3.1 Ответственность сервисов

| Сервис | Bounded Context | Владеет данными | Не делает |
|--------|-----------------|-----------------|-----------|
| **api-gateway** | Edge | сессии, rate-limit, request-id | бизнес-логику |
| **tender-service** | Procurement | tenders, lots, bidders, contracts, amendments | ML, GIS-расчёт |
| **market-service** | Pricing | price_catalog, price_observations, indices | парсинг тендеров |
| **geo-service** | Spatial | geometries, eco_layers, satellite_refs | risk score |
| **risk-engine** | Risk & Explain | risk_assessments, anomalies, explanations, model_versions | UI |
| **ingestion-workers** | Collect | raw_documents, crawl_jobs, source_cursors | публичный API |

### 3.2 Синхрон vs асинхрон

| Взаимодействие | Паттерн | Почему |
|----------------|---------|--------|
| UI → API | Sync REST/JSON | UX latency |
| Ingestion → Domain | Async (Celery + Redis Streams) | долгий scrape |
| Tender created/updated → Risk | Event `tender.upserted` | loose coupling |
| Risk scored → Explanation | Pipeline step / queue | LLM медленнее CatBoost |
| Geo enrichment | Async job | reverse geocode / area calc |

### 3.3 Контракт событий (схема v1)

```json
{
  "event_id": "uuid",
  "event_type": "tender.upserted",
  "occurred_at": "2026-08-05T10:00:00Z",
  "producer": "tender-service",
  "schema_version": 1,
  "payload": {
    "tender_id": "uuid",
    "country_code": "KZ",
    "external_id": "123456",
    "change_hash": "sha256:..."
  }
}
```

Все события версионируются (`schema_version`). Breaking changes → новый тип или v2 topic.

---

## 4. Слои внутри сервиса (гексагональная архитектура)

```
services/<name>/
  app/
    api/              # FastAPI routers (adapters/in)
    domain/           # entities, value objects, policies
    application/      # use-cases / commands / queries
    infrastructure/   # SQLAlchemy, Redis, HTTP clients
    workers/          # Celery tasks (если есть)
  alembic/
  tests/
  Dockerfile
  pyproject.toml
```

**Правило зависимости:** `api → application → domain ← infrastructure`.  
Domain не импортирует FastAPI/SQLAlchemy.

---

## 5. Data flow: от парсера до карты

```mermaid
sequenceDiagram
  participant Cron as Celery Beat
  participant W as Ingestion Worker
  participant S as Source Adapter
  participant Raw as raw_documents
  participant TS as tender-service
  participant MS as market-service
  participant GS as geo-service
  participant RE as risk-engine
  participant LLM as LLM API
  participant UI as Web Map

  Cron->>W: crawl.source(KZ_GOSZAKUP)
  W->>S: fetch_page(cursor)
  S-->>W: HTML/JSON + bytes
  W->>Raw: store + MinIO object
  W->>TS: upsert_tender(normalized)
  TS-->>W: tender_id
  W->>GS: attach_geometry / geocode
  W->>MS: match_work_items
  TS->>RE: event tender.upserted
  RE->>RE: feature engineering
  RE->>RE: CatBoost predict + anomalies
  RE->>LLM: explain(features, score, anomalies)
  LLM-->>RE: explanation_text + reasons[]
  RE->>RE: persist risk_assessment
  UI->>GS: GET /map/features?bbox=
  UI->>RE: GET /risk/{tender_id}
```

Fallback: if `LLM_API_KEY` missing or API errors → `template_explain` (same reasons codes).
---

## 6. Multi-country Source Adapter (критично для масштаба)

```python
# packages/shared/ecotender_shared/ingestion/base.py
from abc import ABC, abstractmethod
from typing import AsyncIterator
from pydantic import BaseModel

class RawTenderPage(BaseModel):
    source_code: str
    country_code: str  # ISO 3166-1 alpha-2
    external_id: str
    fetched_at: str
    content_type: str  # application/json | text/html
    payload: bytes
    checksum: str

class NormalizedTender(BaseModel):
    country_code: str
    external_id: str
    title: str
    description: str | None
    customer_name: str | None
    published_at: str | None
    deadline_at: str | None
    amount: float | None
    currency: str | None
    region_code: str | None
    eco_category: str | None
    participants_count: int | None
    # ... расширяемый словарь extras: dict

class SourceAdapter(ABC):
    source_code: str
    country_code: str

    @abstractmethod
    async def discover(self, cursor: str | None) -> AsyncIterator[str]:
        """Yield external_ids or list URLs."""

    @abstractmethod
    async def fetch(self, ref: str) -> RawTenderPage:
        ...

    @abstractmethod
    def normalize(self, raw: RawTenderPage) -> NormalizedTender:
        ...
```

MVP: реализовать **один** адаптер глубоко (например KZ goszakup) + **fixture adapter** (JSON fixtures) для демо.  
После хакатона: добавить AZ/RU без изменения tender-service.

---

## 7. Безопасность и соответствие (с первого дня)

Даже в MVP закладываем:

1. **RBAC:** `viewer` | `analyst` | `auditor` | `admin`
2. **Audit trail:** кто смотрел/экспортировал риск-карточку (важно для госаудита)
3. **PII minimization:** ФИО должностных лиц — опционально, маскирование в public API
4. **Secrets:** только через env / Docker secrets, никогда в git
5. **CORS / rate limit** на gateway
6. **Idempotency-Key** для write endpoints
7. **Disclaimer:** Risk Score — аналитический индикатор, не юридическое обвинение

---

## 8. Нефункциональные требования (целевые)

| Метрика | MVP | Гос. платформа |
|---------|-----|----------------|
| Latency list API p95 | < 500 ms | < 200 ms |
| Map bbox query p95 | < 800 ms | < 150 ms (tiles) |
| Risk scoring batch | 100 tenders / мин | 10k+ / мин |
| Availability | best-effort | 99.9% |
| Data retention raw | 30 дней | по нормативу (годы) |
| Countries | 1 + fixtures | 5 прикаспийских |

---

## 9. Технологические решения и библиотеки

### Backend
- `fastapi`, `uvicorn[standard]`, `pydantic` v2, `sqlalchemy[asyncio]` 2.x
- `geoalchemy2`, `alembic`, `celery[redis]`, `httpx`, `tenacity`
- `structlog` или `python-json-logger`
- `prometheus-fastapi-instrumentator` (опционально в Day 2)

### Ingestion
- `playwright`, `beautifulsoup4`, `lxml`, `selectolax` (быстрый HTML)
- `pdfplumber` / `pymupdf` для PDF спецификаций
- `hashlib` + content-addressed MinIO keys

### ML / AI
- `catboost`, `pandas`, `numpy`, `scikit-learn`, `optuna` (позже)
- `shap` для feature contribution (опционально в explain)
- `httpx` → OpenAI-compatible Chat Completions API (`LLM_BASE_URL`)
- Template fallback без ключа / при ошибке сети
- `joblib` / native CatBoost model save

### GIS
- PostGIS 3.x, `geoalchemy2`, `shapely`, `geopandas` (offline enrichment)
- Frontend: `leaflet`, `react-leaflet`, optional `leaflet.markercluster`

### Frontend
- React 19+, TypeScript, Vite 6, MUI 7, React Query / TanStack Query
- `react-leaflet` 5 (Leaflet 1.9)
- Zustand (лёгкий UI state), React Router
- i18n (ru/kz/en) — заложить ключи сразу

### Infra
- Docker Compose (dev), позже K8s Helm charts
- Nginx reverse proxy
- MinIO (S3-compatible raw storage)
- Mailhog / stub notifications (позже)

---

## 10. Анти-паттерны, которых избегаем

1. ❌ Один «god service» с парсером + ML + API + UI templates  
2. ❌ Хардкод селекторов парсера внутри domain entities  
3. ❌ Risk Score без версии модели и feature snapshot  
4. ❌ LLM как единственный источник решения о риске  
5. ❌ Геометрия в JSONB без PostGIS indexes  
6. ❌ Отсутствие `external_id` + `source_code` уникальности  

---

## 11. Схема каталогов (полная)

```text
EcoTender AI/
├── README.md
├── .env.example
├── docker-compose.yml
├── docker-compose.override.yml
├── Makefile
├── apps/
│   └── web/
│       ├── package.json
│       ├── vite.config.ts
│       ├── index.html
│       └── src/
│           ├── app/
│           ├── features/
│           │   ├── map/
│           │   ├── tenders/
│           │   ├── risk/
│           │   └── auth/
│           ├── shared/
│           └── main.tsx
├── services/
│   ├── api-gateway/
│   ├── tender-service/
│   ├── market-service/
│   ├── geo-service/
│   ├── risk-engine/
│   └── ingestion-workers/
├── packages/
│   └── shared/
│       └── ecotender_shared/
│           ├── schemas/
│           ├── events/
│           ├── enums/
│           └── ingestion/
├── ml/
│   ├── notebooks/
│   ├── training/
│   ├── features/
│   ├── models/           # .cbm артефакты (git-lfs / MinIO)
│   └── evaluation/
├── infra/
│   ├── postgres/init/
│   │   └── 01_extensions.sql
│   ├── nginx/
│   └── otel/
└── docs/
```

См. также: [ER_DIAGRAM.md](ER_DIAGRAM.md), [ML_RISK_ENGINE.md](ML_RISK_ENGINE.md), [API.md](API.md), [MVP_48H.md](MVP_48H.md), [SCALING.md](SCALING.md).
