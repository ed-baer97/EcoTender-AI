**Тіл / Language:** [Русский](../ru/API.md) · [English](../en/API.md) · [Қазақша](API.md)

# REST API (контрактілер v1)

Base URL: `http://localhost:8000/api/v1`  
Gateway сервистерге прокси арқылы бағыттайды. Барлық жауаптар — JSON, қателер — RFC7807-like.

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
- `Authorization: Bearer <jwt>` (public map MVP-де auth-сыз болуы мүмкін)
- `X-Request-Id`
- `Idempotency-Key` POST-та

---

## Auth

| Method | Path | Сипаттама |
|--------|------|----------|
| POST | `/auth/login` | email/password → JWT |
| POST | `/auth/refresh` | refresh token |
| GET | `/auth/me` | ағымдағы пайдаланушы |

## Admin (role: admin)

| Method | Path | Сипаттама |
|--------|------|----------|
| GET | `/admin/overview` | сервистер мәртебесі + кілттер дайындығы |
| GET | `/admin/secrets` | кілттер каталогы (құпия мәндер маскаланған) |
| PUT | `/admin/secrets/{key}` | runtime-кілтті сақтау (Redis + file) |
| DELETE | `/admin/secrets/{key}` | runtime-мәнді жою (`.env` қалады) |
| POST | `/admin/secrets/LLM_API_KEY/test` | LLM API тексеру |
| GET | `/admin/audit` | кілт өзгерістерінің аудиті |

Кілттер: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_PROVIDER`, `GOSZAKUP_TOKEN`, `GOSZAKUP_BASE_URL`.  
Demo admin: `admin@ecotender.kz` / `admin123`.

Рөлдер: `viewer`, `analyst`, `auditor`, `admin`.

---

## Tenders

| Method | Path | Сипаттама |
|--------|------|----------|
| GET | `/tenders` | сүзгілер: country, region, eco_category, risk_band, q, date_from, date_to, page, size |
| GET | `/tenders/{id}` | тендер карточкасы |
| GET | `/tenders/{id}/participants` | қатысушылар |
| GET | `/tenders/{id}/contract` | шарт + amendments |
| GET | `/tenders/{id}/work-items` | смета позициялары |
| POST | `/tenders/reindex` | admin: туындыларды қайта есептеу |

### Тізім мысалы

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

| Method | Path | Сипаттама |
|--------|------|----------|
| GET | `/tenders/{id}/risk` | соңғы assessment + reasons + anomalies |
| POST | `/tenders/{id}/risk/rescore` | analyst+: қайта есептеу |
| GET | `/risk/top` | ең тәуекелділер тобы |
| GET | `/risk/models` | модельдер тізілімі |

### Risk card мысалы

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

| Method | Path | Сипаттама |
|--------|------|----------|
| GET | `/map/features` | bbox + layers → GeoJSON FeatureCollection |
| GET | `/map/tenders/{id}/geometry` | жұмыс полигоны |
| GET | `/map/layers` | қолжетімді қабаттар |
| GET | `/map/layers/{code}/features` | bbox ішіндегі eco layer features |

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

| Method | Path | Сипаттама |
|--------|------|----------|
| GET | `/market/items` | каталог |
| GET | `/market/items/{id}/prices` | бағалар тарихы |
| POST | `/market/estimate` | work_items бойынша смета бағалауы |

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

| Method | Path | Сипаттама |
|--------|------|----------|
| GET | `/ingest/sources` | адаптерлер тізімі |
| POST | `/ingest/sources/{code}/run` | crawl іске қосу |
| GET | `/ingest/jobs` | job мәртебелері |
| GET | `/ingest/jobs/{id}` | егжей-тегжей |

---

## Health

| Method | Path |
|--------|------|
| GET | `/health` |
| GET | `/ready` | PG/Redis тексеру |

---

## OpenAPI

Әр сервис `/docs` жариялайды. Gateway бірыңғай swagger жинайды немесе links қайтарады:

```
GET /api/openapi.json
```

Нұсқалау: `/api/v1` → `/api/v2` breaking changes кезінде; deprecation headers.
