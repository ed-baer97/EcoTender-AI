**Тіл / Language:** [Русский](../ru/ARCHITECTURE.md) · [English](../en/ARCHITECTURE.md) · [Қазақша](ARCHITECTURE.md)

# EcoTender AI — Платформа архитектурасы

## 1. Жобалық принцип: «Production-shaped MVP»

Біз бір FastAPI + SQLite үстінде демо **салмаймыз**.  
Біз **production-архитектураның жұқа қимасын** құрамыз:

| Принцип | MVP-дегі іске асыру (48с) | Хакатоннан кейінгі масштаб |
|---------|------------------------|------------------------|
| Bounded contexts | Анық API-лары бар бөлек сервистер | Тәуелсіз deploy/scaling |
| Көз адаптерлері | `SourceAdapter` interface + 1–2 ел | KZ/AZ/RU/TM/IR плагиндері |
| Оқиғалар | Redis Streams (outbox) | Kafka / NATS JetStream |
| Идемпотенттілік | `external_id` + upsert | Exactly-once ingestion |
| Аудит | `audit_log` table + middleware | SIEM / WORM storage |
| Auth | JWT + roles (viewer/analyst/admin) | SSO (Keycloak / ЕСИА / eGov) |
| Observability | structured JSON logs + health | OpenTelemetry + Prometheus |
| Feature flags | env + DB flags | LaunchDarkly / Unleash |
| GIS | PostGIS + tile layers | Vector tiles (Martin/pg_tileserv) |
| AI | CatBoost + LLM API (OpenAI-compatible) | Private LLM / VPC endpoint |

**Ереже:** кез келген хакатондық shortcut **алмастырылатын адаптер** болуы керек, домендік логикаға қатты тігілмеуі тиіс.

---

## 2. Контексттік карта (C4 Level 1)

```mermaid
flowchart TB
  subgraph Actors
    Analyst[Аналитик / аудитор]
    Public[Ашық бақылаушы]
    Admin[Платформа әкімшісі]
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
    GZ[Мемлекеттік сатып алу порталдары]
    Market[Нарықтық каталогтар]
    Sat[Спутниктік API]
    EcoDB[Эко-тізілімдер]
    OSM[OSM / жағалау сызығы]
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

## 3. Микросервистер (C4 Level 2)

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

> **AI split:** CatBoost artifact `risk-engine`-де тұрады (өз шешімі).  
> Түсіндіру сыртқы `LLM_BASE_URL` + `LLM_API_KEY` арқылы өтеді.  
> Кілтсіз → детерминистік `template_fallback` (demo-safe offline).
### 3.1 Сервистердің жауапкершілігі

| Сервис | Bounded Context | Деректерге ие | Жасамайды |
|--------|-----------------|-----------------|-----------|
| **api-gateway** | Edge | сессиялар, rate-limit, request-id | бизнес-логика |
| **tender-service** | Procurement | tenders, lots, bidders, contracts, amendments | ML, GIS-есеп |
| **market-service** | Pricing | price_catalog, price_observations, indices | тендерлерді парсинг |
| **geo-service** | Spatial | geometries, eco_layers, satellite_refs | risk score |
| **risk-engine** | Risk & Explain | risk_assessments, anomalies, explanations, model_versions | UI |
| **ingestion-workers** | Collect | raw_documents, crawl_jobs, source_cursors | ашық API |

### 3.2 Синхрон vs асинхрон

| Өзара әрекет | Паттерн | Неге |
|----------------|---------|--------|
| UI → API | Sync REST/JSON | UX latency |
| Ingestion → Domain | Async (Celery + Redis Streams) | ұзақ scrape |
| Tender created/updated → Risk | Event `tender.upserted` | loose coupling |
| Risk scored → Explanation | Pipeline step / queue | LLM CatBoost-тан баяу |
| Geo enrichment | Async job | reverse geocode / area calc |

### 3.3 Оқиғалар контракты (схема v1)

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

Барлық оқиғалар нұсқаланады (`schema_version`). Breaking changes → жаңа тип немесе v2 topic.

---

## 4. Сервис ішіндегі қабаттар (гексагоналды архитектура)

```
services/<name>/
  app/
    api/              # FastAPI routers (adapters/in)
    domain/           # entities, value objects, policies
    application/      # use-cases / commands / queries
    infrastructure/   # SQLAlchemy, Redis, HTTP clients
    workers/          # Celery tasks (егер бар болса)
  alembic/
  tests/
  Dockerfile
  pyproject.toml
```

**Тәуелділік ережесі:** `api → application → domain ← infrastructure`.  
Domain FastAPI/SQLAlchemy импорттамайды.

---

## 5. Data flow: парсерден картаға дейін

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

Fallback: егер `LLM_API_KEY` жоқ немесе API қателессе → `template_explain` (сол reasons codes).
---

## 6. Multi-country Source Adapter (масштаб үшін маңызды)

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
    # ... кеңейтілетін сөздік extras: dict

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

MVP: **бір** адаптерді терең іске асыру (мысалы KZ goszakup) + демо үшін **fixture adapter** (JSON fixtures).  
Хакатоннан кейін: tender-service өзгертпей AZ/RU қосу.

---

## 7. Қауіпсіздік және сәйкестік (бірінші күннен)

MVP-де де қалаймыз:

1. **RBAC:** `viewer` | `analyst` | `auditor` | `admin`
2. **Audit trail:** кім тәуекел-карточканы көрді/экспорттады (мемлекеттік аудит үшін маңызды)
3. **PII minimization:** лауазымды тұлғалардың АТЖ — опционалды, public API-да маскалау
4. **Secrets:** тек env / Docker secrets арқылы, ешқашан git-те емес
5. **CORS / rate limit** gateway-де
6. **Idempotency-Key** write endpoints үшін
7. **Disclaimer:** Risk Score — аналитикалық индикатор, заңды айыптау емес

---

## 8. Функционалды емес талаптар (мақсатты)

| Метрика | MVP | Мемл. платформа |
|---------|-----|----------------|
| Latency list API p95 | < 500 ms | < 200 ms |
| Map bbox query p95 | < 800 ms | < 150 ms (tiles) |
| Risk scoring batch | 100 tenders / мин | 10k+ / мин |
| Availability | best-effort | 99.9% |
| Data retention raw | 30 күн | норматив бойынша (жылдар) |
| Countries | 1 + fixtures | 5 Каспий маңы |

---

## 9. Технологиялық шешімдер және кітапханалар

### Backend
- `fastapi`, `uvicorn[standard]`, `pydantic` v2, `sqlalchemy[asyncio]` 2.x
- `geoalchemy2`, `alembic`, `celery[redis]`, `httpx`, `tenacity`
- `structlog` немесе `python-json-logger`
- `prometheus-fastapi-instrumentator` (Day 2-де опционалды)

### Ingestion
- `playwright`, `beautifulsoup4`, `lxml`, `selectolax` (жылдам HTML)
- `pdfplumber` / `pymupdf` PDF спецификациялар үшін
- `hashlib` + content-addressed MinIO keys

### ML / AI
- `catboost`, `pandas`, `numpy`, `scikit-learn`, `optuna` (кейін)
- `shap` feature contribution үшін (explain-те опционалды)
- `httpx` → OpenAI-compatible Chat Completions API (`LLM_BASE_URL`)
- Кілтсіз / желі қатесінде template fallback
- `joblib` / native CatBoost model save

### GIS
- PostGIS 3.x, `geoalchemy2`, `shapely`, `geopandas` (offline enrichment)
- Frontend: `leaflet`, `react-leaflet`, optional `leaflet.markercluster`

### Frontend
- React 19+, TypeScript, Vite 6, MUI 7, React Query / TanStack Query
- `react-leaflet` 5 (Leaflet 1.9)
- Zustand (жеңіл UI state), React Router
- i18n (ru/kz/en) — кілттерді бірден қалау

### Infra
- Docker Compose (dev), кейін K8s Helm charts
- Nginx reverse proxy
- MinIO (S3-compatible raw storage)
- Mailhog / stub notifications (кейін)

---

## 10. Ауылатылатын анти-паттерндер

1. ❌ Парсер + ML + API + UI templates бар бір «god service»  
2. ❌ Парсер селекторларын domain entities ішінде хардкодтау  
3. ❌ Модель нұсқасы мен feature snapshot жоқ Risk Score  
4. ❌ LLM-ді тәуекел туралы шешімнің жалғыз көзі ретінде пайдалану  
5. ❌ PostGIS indexes жоқ JSONB-дегі геометрия  
6. ❌ `external_id` + `source_code` бірегейлігінің жоқтығы  

---

## 11. Каталогтар схемасы (толық)

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
│   ├── models/           # .cbm артефактілер (git-lfs / MinIO)
│   └── evaluation/
├── infra/
│   ├── postgres/init/
│   │   └── 01_extensions.sql
│   ├── nginx/
│   └── otel/
└── docs/
```

Сондай-ақ қараңыз: [ER_DIAGRAM.md](ER_DIAGRAM.md), [ML_RISK_ENGINE.md](ML_RISK_ENGINE.md), [API.md](API.md), [SCALING.md](SCALING.md).
