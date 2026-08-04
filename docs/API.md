# REST API (контракты v1)

Base URL: `http://localhost:8000/api/v1`  
Gateway проксирует в сервисы. Все ответы — JSON, ошибки — RFC7807-like.

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
- `Authorization: Bearer <jwt>` (public map может быть без auth в MVP)
- `X-Request-Id`
- `Idempotency-Key` на POST

---

## Auth

| Method | Path | Описание |
|--------|------|----------|
| POST | `/auth/login` | email/password → JWT |
| POST | `/auth/refresh` | refresh token |
| GET | `/auth/me` | текущий пользователь |

Роли: `viewer`, `analyst`, `auditor`, `admin`.

---

## Tenders

| Method | Path | Описание |
|--------|------|----------|
| GET | `/tenders` | фильтры: country, region, eco_category, risk_band, q, date_from, date_to, page, size |
| GET | `/tenders/{id}` | карточка тендера |
| GET | `/tenders/{id}/participants` | участники |
| GET | `/tenders/{id}/contract` | контракт + amendments |
| GET | `/tenders/{id}/work-items` | позиции сметы |
| POST | `/tenders/reindex` | admin: пересчёт дериватов |

### Пример списка

`GET /tenders?country=KZ&risk_band=high&size=20`

```json
{
  "items": [
    {
      "id": "8f2c...",
      "external_id": "123456",
      "title": "Рекультивация прибрежной зоны",
      "country_code": "KZ",
      "region_name": "Мангистауская область",
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

| Method | Path | Описание |
|--------|------|----------|
| GET | `/tenders/{id}/risk` | последний assessment + reasons + anomalies |
| POST | `/tenders/{id}/risk/rescore` | analyst+: пересчёт |
| GET | `/risk/top` | топ рисковых |
| GET | `/risk/models` | реестр моделей |

### Пример risk card

```json
{
  "tender_id": "8f2c...",
  "risk_score": 82,
  "risk_band": "critical",
  "corruption_proba": 0.82,
  "model_version": "catboost-2026.08.05-a1",
  "scored_at": "2026-08-05T12:00:00Z",
  "explanation": "Стоимость превышает рыночную на 47%. Подрядчик регулярно выигрывает аналогичные тендеры при минимальном числе участников. Рекомендуется аудит.",
  "explanation_meta": {
    "provider": "openai",
    "model": "gpt-5.6-terra",
    "prompt_version": "explain-v1-ru",
    "source": "llm_api"
  },
  "reasons": [
    {"code": "OVERPRICE", "severity": "high", "message_ru": "Превышение рынка на 47%", "contribution": 0.22},
    {"code": "SINGLE_BIDDER", "severity": "high", "message_ru": "Единственный участник", "contribution": 0.18},
    {"code": "REPEAT_WINNER", "severity": "medium", "message_ru": "Высокая доля побед подрядчика", "contribution": 0.14}
  ],
  "anomalies": [
    {"anomaly_type": "PRICE_OUTLIER", "severity": 0.91, "evidence": {"overprice_ratio": 1.47}}
  ],
  "feature_vector": {"overprice_ratio": 1.47, "participants_count": 1}
}
```

---

## Map / Geo

| Method | Path | Описание |
|--------|------|----------|
| GET | `/map/features` | bbox + layers → GeoJSON FeatureCollection |
| GET | `/map/tenders/{id}/geometry` | полигон работ |
| GET | `/map/layers` | доступные слои |
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
        "title": "Рекультивация...",
        "risk_score": 82,
        "risk_band": "critical"
      }
    }
  ]
}
```

---

## Market

| Method | Path | Описание |
|--------|------|----------|
| GET | `/market/items` | каталог |
| GET | `/market/items/{id}/prices` | история цен |
| POST | `/market/estimate` | оценка сметы по work_items |

```json
POST /market/estimate
{
  "work_items": [
    {"name": "Вывоз нефтезагрязнённого грунта", "unit": "m3", "quantity": 1200}
  ],
  "region_code": "KZ-MAN"
}
```

---

## Ingestion (admin)

| Method | Path | Описание |
|--------|------|----------|
| GET | `/ingest/sources` | список адаптеров |
| POST | `/ingest/sources/{code}/run` | запуск crawl |
| GET | `/ingest/jobs` | статус job'ов |
| GET | `/ingest/jobs/{id}` | детали |

---

## Health

| Method | Path |
|--------|------|
| GET | `/health` |
| GET | `/ready` | проверка PG/Redis |

---

## OpenAPI

Каждый сервис публикует `/docs`. Gateway собирает единый swagger или отдаёт links:

```
GET /api/openapi.json
```

Версионирование: `/api/v1` → `/api/v2` при breaking changes; deprecation headers.
