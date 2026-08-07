**Language:** [Русский](../ru/API.md) · [English](API.md) · [Қазақша](../kk/API.md)

# REST API (v1 Contracts)

Base URL: `http://localhost:8000/api/v1`  
Gateway proxies to services. All responses are JSON; errors are RFC7807-like.

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Tender not found",
  "instance": "/api/v1/tenders/..."
}
```

Headers:
- `Authorization: Bearer <jwt>` (public map may be unauthenticated in MVP)
- `X-Request-Id`
- `Idempotency-Key` on POST

---

## Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | email/password → JWT |
| POST | `/auth/refresh` | refresh token |
| GET | `/auth/me` | current user |

## Admin (role: admin)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/overview` | service status + key readiness |
| GET | `/admin/secrets` | key catalog (secret values masked) |
| PUT | `/admin/secrets/{key}` | save runtime key (Redis + file) |
| DELETE | `/admin/secrets/{key}` | delete runtime value (`.env` remains) |
| POST | `/admin/secrets/LLM_API_KEY/test` | LLM API check |
| GET | `/admin/audit` | audit of key changes |

Keys: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_PROVIDER`, `GOSZAKUP_TOKEN`, `GOSZAKUP_BASE_URL`.  
Demo admin: `admin@ecotender.kz` / `admin123`.

Roles: `viewer`, `analyst`, `auditor`, `admin`.

---

## Tenders

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tenders` | filters: country, region, eco_category, risk_band, q, date_from, date_to, page, size |
| GET | `/tenders/{id}` | tender card |
| GET | `/tenders/{id}/participants` | participants |
| GET | `/tenders/{id}/contract` | contract + amendments |
| GET | `/tenders/{id}/work-items` | estimate line items |
| POST | `/tenders/reindex` | admin: recompute derivatives |

### List Example

`GET /tenders?country=KZ&risk_band=high&size=20`

```json
{
  "items": [
    {
      "id": "8f2c...",
      "external_id": "123456",
      "title": "Coastal zone reclamation",
      "country_code": "KZ",
      "region_name": "Mangystau Region",
      "amount": 450000000,
      "currency": "KZT",
      "eco_category": "coastal_cleanup",
      "participants_count": 1,
      "risk_score": 82,
      "risk_band": "critical",
      "centroid": {"lat": 43.65, "lon": 51.15}
    }
  ],
  "page": 1,
  "size": 20,
  "total": 137
}
```

---

## Risk

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tenders/{id}/risk` | latest assessment + reasons + anomalies |
| POST | `/tenders/{id}/risk/rescore` | analyst+: rescore |
| GET | `/risk/top` | top risky |
| GET | `/risk/models` | model registry |

### Risk Card Example

```json
{
  "tender_id": "8f2c...",
  "risk_score": 82,
  "risk_band": "critical",
  "corruption_proba": 0.82,
  "model_version": "catboost-2026.08.05-a1",
  "scored_at": "2026-08-05T12:00:00Z",
  "explanation": "Cost exceeds market by 47%. The contractor regularly wins similar tenders with a minimal number of participants. Audit recommended.",
  "explanation_meta": {
    "provider": "openai",
    "model": "gpt-5.6-terra",
    "prompt_version": "explain-v1-ru",
    "source": "llm_api"
  },
  "reasons": [
    {"code": "OVERPRICE", "severity": "high", "message_ru": "Exceeds market by 47%", "contribution": 0.22},
    {"code": "SINGLE_BIDDER", "severity": "high", "message_ru": "Single participant", "contribution": 0.18},
    {"code": "REPEAT_WINNER", "severity": "medium", "message_ru": "High contractor win share", "contribution": 0.14}
  ],
  "anomalies": [
    {"anomaly_type": "PRICE_OUTLIER", "severity": 0.91, "evidence": {"overprice_ratio": 1.47}}
  ],
  "feature_vector": {"overprice_ratio": 1.47, "participants_count": 1}
}
```

---

## Map / Geo

| Method | Path | Description |
|--------|------|-------------|
| GET | `/map/features` | bbox + layers → GeoJSON FeatureCollection |
| GET | `/map/tenders/{id}/geometry` | work polygon |
| GET | `/map/layers` | available layers |
| GET | `/map/layers/{code}/features` | eco layer features in bbox |

`GET /map/features?bbox=48.0,38.0,54.0,47.0&layers=tenders,coastline,protected&min_risk=60`

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [51.15, 43.65]},
      "properties": {
        "kind": "tender",
        "tender_id": "8f2c...",
        "title": "Reclamation...",
        "risk_score": 82,
        "risk_band": "critical"
      }
    }
  ]
}
```

---

## Market

| Method | Path | Description |
|--------|------|-------------|
| GET | `/market/items` | catalog |
| GET | `/market/items/{id}/prices` | price history |
| POST | `/market/estimate` | estimate costing from work_items |

```json
POST /market/estimate
{
  "work_items": [
    {"name": "Removal of oil-contaminated soil", "unit": "m3", "quantity": 1200}
  ],
  "region_code": "KZ-MAN"
}
```

---

## Ingestion (admin)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ingest/sources` | adapter list |
| POST | `/ingest/sources/{code}/run` | start crawl |
| GET | `/ingest/jobs` | job statuses |
| GET | `/ingest/jobs/{id}` | details |

---

## Health

| Method | Path |
|--------|------|
| GET | `/health` |
| GET | `/ready` | PG/Redis check |

---

## OpenAPI

Each service publishes `/docs`. Gateway aggregates a unified swagger or returns links:

```
GET /api/openapi.json
```

Versioning: `/api/v1` → `/api/v2` on breaking changes; deprecation headers.
