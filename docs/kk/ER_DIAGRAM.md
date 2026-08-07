**Тіл / Language:** [Русский](../ru/ER_DIAGRAM.md) · [English](../en/ER_DIAGRAM.md) · [Қазақша](ER_DIAGRAM.md)

# ER-диаграмма және деректер моделі

## Модельдеу принциптері

1. **Source of truth:** PostgreSQL-дағы нормаланған домендік кестелер.
2. **Raw immutable:** `raw_documents` — append-only (аудит үшін дәлелдік база).
3. **Spatial first:** геометриялар тек PostGIS арқылы (`geometry` / `geography`).
4. **ML reproducibility:** әр `risk_assessment` `model_version` + `feature_vector` (JSONB) сақтайды.
5. **Multi-country:** сатып алулардың барлық мәндерінде `country_code`.
6. **Soft delete** тек пайдаланушы мәндері үшін; сатып алу деректері — versioned upsert.

---

## Mermaid ER

```mermaid
erDiagram
  COUNTRY ||--o{ REGION : has
  REGION ||--o{ TENDER : located_in
  CUSTOMER ||--o{ TENDER : publishes
  SOURCE ||--o{ TENDER : originates
  SOURCE ||--o{ RAW_DOCUMENT : stores
  TENDER ||--o{ LOT : contains
  TENDER ||--o{ BIDDER_PARTICIPATION : has
  CONTRACTOR ||--o{ BIDDER_PARTICIPATION : participates
  CONTRACTOR ||--o{ CONTRACT : wins
  TENDER ||--o| CONTRACT : results_in
  CONTRACT ||--o{ AMENDMENT : modified_by
  TENDER ||--o| TENDER_GEOMETRY : has
  TENDER ||--o{ WORK_ITEM : specifies
  WORK_ITEM }o--o| PRICE_OBSERVATION : compared_to
  MARKET_ITEM ||--o{ PRICE_OBSERVATION : priced_as
  TENDER ||--o{ RISK_ASSESSMENT : scored
  RISK_ASSESSMENT ||--o{ RISK_REASON : explains
  RISK_ASSESSMENT ||--o{ ANOMALY_FLAG : flags
  ECO_LAYER ||--o{ ECO_FEATURE : contains
  TENDER_GEOMETRY }o--o{ ECO_FEATURE : intersects
  MODEL_REGISTRY ||--o{ RISK_ASSESSMENT : produced_by
  USER_ACCOUNT ||--o{ AUDIT_LOG : performs
  CRAWL_JOB ||--o{ RAW_DOCUMENT : produces

  COUNTRY {
    char2 code PK
    string name
  }

  REGION {
    uuid id PK
    char2 country_code FK
    string code
    string name
    geometry boundary
  }

  SOURCE {
    string code PK
    char2 country_code
    string name
    string base_url
    string adapter_class
    boolean is_active
  }

  CUSTOMER {
    uuid id PK
    char2 country_code
    string external_id
    string name
    string inn_bin
  }

  CONTRACTOR {
    uuid id PK
    char2 country_code
    string external_id
    string name
    string inn_bin
    int wins_count
    float win_rate
    jsonb reputation_stats
  }

  TENDER {
    uuid id PK
    string source_code FK
    char2 country_code
    string external_id
    string title
    text description
    uuid customer_id FK
    uuid region_id FK
    timestamptz published_at
    timestamptz deadline_at
    numeric amount
    char3 currency
    string status
    string eco_category
    string procurement_method
    int participants_count
    numeric area_sq_m
    int duration_days
    string change_hash
    timestamptz ingested_at
    timestamptz updated_at
  }

  LOT {
    uuid id PK
    uuid tender_id FK
    string lot_number
    string title
    numeric amount
  }

  BIDDER_PARTICIPATION {
    uuid id PK
    uuid tender_id FK
    uuid contractor_id FK
    numeric bid_amount
    boolean is_winner
    int rank
  }

  CONTRACT {
    uuid id PK
    uuid tender_id FK
    uuid contractor_id FK
    numeric signed_amount
    date signed_at
    date end_at
    string status
  }

  AMENDMENT {
    uuid id PK
    uuid contract_id FK
    date amended_at
    numeric amount_delta
    int days_delta
    text rationale
  }

  TENDER_GEOMETRY {
    uuid tender_id PK_FK
    geometry geom
    string geom_source
    float confidence
    geography centroid
  }

  WORK_ITEM {
    uuid id PK
    uuid tender_id FK
    string name
    string unit
    numeric quantity
    numeric unit_price
    string matched_market_sku
  }

  MARKET_ITEM {
    uuid id PK
    string sku
    string name
    string unit
    string category
    char2 country_code
  }

  PRICE_OBSERVATION {
    uuid id PK
    uuid market_item_id FK
    numeric price
    char3 currency
    date observed_on
    string source
    string region_code
  }

  MODEL_REGISTRY {
    string version PK
    string algorithm
    jsonb hyperparams
    jsonb metrics
    string artifact_uri
    timestamptz trained_at
    boolean is_active
  }

  RISK_ASSESSMENT {
    uuid id PK
    uuid tender_id FK
    string model_version FK
    float risk_score
    float corruption_proba
    string risk_band
    jsonb feature_vector
    jsonb shap_values
    timestamptz scored_at
  }

  RISK_REASON {
    uuid id PK
    uuid assessment_id FK
    string code
    string severity
    text message_ru
    float contribution
  }

  ANOMALY_FLAG {
    uuid id PK
    uuid assessment_id FK
    string anomaly_type
    float severity
    jsonb evidence
  }

  ECO_LAYER {
    string code PK
    string name
    string layer_type
    string attribution
  }

  ECO_FEATURE {
    uuid id PK
    string layer_code FK
    string name
    geometry geom
    jsonb properties
  }

  RAW_DOCUMENT {
    uuid id PK
    string source_code FK
    string external_ref
    string content_type
    string checksum
    string storage_uri
    jsonb headers
    timestamptz fetched_at
  }

  CRAWL_JOB {
    uuid id PK
    string source_code
    string status
    string cursor
    int pages_ok
    int pages_fail
    timestamptz started_at
    timestamptz finished_at
  }

  USER_ACCOUNT {
    uuid id PK
    string email
    string role
    boolean is_active
    timestamptz created_at
  }

  AUDIT_LOG {
    uuid id PK
    uuid user_id FK
    string action
    string resource_type
    string resource_id
    jsonb meta
    timestamptz created_at
  }
```

---

## Негізгі шектеулер және индекстер

```sql
-- Көздегі тендердің бірегейлігі
CREATE UNIQUE INDEX uq_tender_source_ext
  ON tender (source_code, external_id);

-- Тәуекел және ел бойынша іздеу
CREATE INDEX ix_tender_country_published
  ON tender (country_code, published_at DESC);

CREATE INDEX ix_risk_score ON risk_assessment (risk_score DESC);

-- Кеңістіктік индекстер
CREATE INDEX ix_tender_geom ON tender_geometry USING GIST (geom);
CREATE INDEX ix_eco_feature_geom ON eco_feature USING GIST (geom);
CREATE INDEX ix_region_boundary ON region USING GIST (boundary);

-- map bbox үшін
-- ST_Intersects(geom, ST_MakeEnvelope(minx,miny,maxx,maxy,4326))
```

---

## Risk band (канон)

| Band | Score | UI color intent |
|------|-------|-----------------|
| `low` | 0–29 | green |
| `medium` | 30–59 | amber |
| `high` | 60–79 | orange |
| `critical` | 80–100 | red |

Шектер — `risk_engine` конфигінде, UI-да хардкод емес.

---

## Миграциялар

- Әр сервиске бір Alembic **немесе** schema-per-service бар shared migration runner:
  - MVP: **бір БД, схемалар:** `tender`, `market`, `geo`, `risk`, `ingest`, `iam`
  - Scale: логикалық схемаларды сақтай отырып БД-ны физикалық бөлу

```sql
CREATE SCHEMA IF NOT EXISTS tender;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS risk;
CREATE SCHEMA IF NOT EXISTS ingest;
CREATE SCHEMA IF NOT EXISTS iam;
```

Бұл кейін схемаларды доменді қайта жазбай бөлек инстанстарға шығаруға мүмкіндік береді.
