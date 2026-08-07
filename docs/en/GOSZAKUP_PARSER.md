**Language:** [Русский](../ru/GOSZAKUP_PARSER.md) · [English](GOSZAKUP_PARSER.md) · [Қазақша](../kk/GOSZAKUP_PARSER.md)

# goszakup.gov.kz Parser

## Ingestion Modes

| Mode | When | `source_code` | `mode` in crawl response |
|------|------|---------------|--------------------------|
| **OWS v3 API** | `GOSZAKUP_TOKEN` is set | `KZ_GOSZAKUP_OWS_V3` | `live_api` |
| **Playwright stub** | no token, `GOSZAKUP_USE_PLAYWRIGHT=true` | `KZ_GOSZAKUP_PLAYWRIGHT` or the same OWS code | `playwright_stub` |
| **Offline sample** | no token, Playwright disabled | `KZ_GOSZAKUP_OWS_V3` | `sample_offline` |

API documentation: [OWS v3](https://goszakup.gov.kz/ru/developer/ows_v3) · [OWS v2](https://goszakup.gov.kz/ru/developer/ows_v2)

## What Is Implemented

| Component | Path |
|-----------|------|
| OWS adapter | `packages/shared/ecotender_shared/ingestion/goszakup_kz.py` |
| Playwright stub | `packages/shared/ecotender_shared/ingestion/goszakup_playwright.py` |
| HTML parser | `packages/shared/ecotender_shared/ingestion/goszakup_html.py` |
| Factory (mode selection) | `packages/shared/ecotender_shared/ingestion/goszakup_factory.py` |
| Eco filter | `eco_filter.py` |
| Celery task | `app.workers.tasks.crawl_source` |
| HTML fixtures (tests / offline) | `data/fixtures/html/` |

## OWS v3 (production)

1. Token: JSC “Center of Electronic Finance” or Profile → “Issue token”.
2. `.env`: `GOSZAKUP_TOKEN=<token>`
3. Base: `https://ows.goszakup.gov.kz`
4. Endpoints: `GET /v3/trd-buy/all`, `GET /v3/trd-buy/{id}`

## Playwright Stub (no token)

Parses the public portal: [announcement search](https://goszakup.gov.kz/ru/search/announce).

By default we take **completed** procurements (not open bid submission):

- `filter[status][]=350` — announcement status “Completed”;
- `filter[signs][]=is_not_active` — “Inactive/completed”;
- after detail fetch: contract status **Active** or **Executed** (incl. “Transferred.Active” / “Transferred.Executed”).

```env
GOSZAKUP_USE_PLAYWRIGHT=true
GOSZAKUP_PW_KEYWORD=экология
GOSZAKUP_PW_REGION_ONLY=mangystau
GOSZAKUP_PW_BROWSE_RECENT=false
GOSZAKUP_PW_MAX_ITEMS=30
GOSZAKUP_PW_FETCH_DETAIL=true
GOSZAKUP_PW_FILTER_STATUS=350
GOSZAKUP_PW_FILTER_SIGNS=is_not_active
GOSZAKUP_PW_CONTRACT_STATUSES=действует,исполнен
GOSZAKUP_PW_REQUIRE_CONTRACT_STATUS=true
# GOSZAKUP_PW_OFFLINE=true   # HTML fixtures only, no browser
```

By default the scraper takes only Mangystau Region (`GOSZAKUP_PW_REGION_ONLY=mangystau`):

- main portal filter `filter[kato]=470000000` (KATO of Mangystau Region);
- extra search by customer/toponyms + post-filter on text;
- `map_kz_region` no longer substitutes Mangystau “by default” for other regions.

```bash
# explicit Playwright source
curl -X POST http://localhost:8000/api/v1/ingest/sources/KZ_GOSZAKUP_PLAYWRIGHT/run

# or the same OWS crawl — factory switches to Playwright if there is no token
curl -X POST http://localhost:8000/api/v1/ingest/sources/KZ_GOSZAKUP_OWS_V3/run
```

Verification:

```bash
curl "http://localhost:8000/api/v1/tenders?source_code=KZ_GOSZAKUP_PLAYWRIGHT&country=KZ"
```

Parser tests (offline):

```bash
pip install -e "packages/shared[playwright]" beautifulsoup4 lxml
pytest packages/shared/tests/test_goszakup_html.py -q
```

## Running Crawl (common)

```bash
docker compose up -d --build ingestion-worker
# Flower: http://localhost:5555
```
