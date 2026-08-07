**Тіл / Language:** [Русский](../ru/GOSZAKUP_PARSER.md) · [English](../en/GOSZAKUP_PARSER.md) · [Қазақша](GOSZAKUP_PARSER.md)

# goszakup.gov.kz парсері

## Ingestion режимдері

| Режим | Қашан | `source_code` | crawl жауабындағы `mode` |
|-------|--------|---------------|------------------------|
| **OWS v3 API** | `GOSZAKUP_TOKEN` бар | `KZ_GOSZAKUP_OWS_V3` | `live_api` |
| **Playwright stub** | токен жоқ, `GOSZAKUP_USE_PLAYWRIGHT=true` | `KZ_GOSZAKUP_PLAYWRIGHT` немесе сол OWS code | `playwright_stub` |
| **Offline sample** | токен жоқ, Playwright өшірулі | `KZ_GOSZAKUP_OWS_V3` | `sample_offline` |

API құжаттамасы: [OWS v3](https://goszakup.gov.kz/ru/developer/ows_v3) · [OWS v2](https://goszakup.gov.kz/ru/developer/ows_v2)

## Не іске асырылған

| Компонент | Жол |
|-----------|------|
| OWS adapter | `packages/shared/ecotender_shared/ingestion/goszakup_kz.py` |
| Playwright stub | `packages/shared/ecotender_shared/ingestion/goszakup_playwright.py` |
| HTML parser | `packages/shared/ecotender_shared/ingestion/goszakup_html.py` |
| Factory (режимді таңдау) | `packages/shared/ecotender_shared/ingestion/goszakup_factory.py` |
| Eco-сүзгі | `eco_filter.py` |
| Celery task | `app.workers.tasks.crawl_source` |
| HTML fixtures (тесттер / offline) | `data/fixtures/html/` |

## OWS v3 (production)

1. Токен: АҚ «Электрондық қаржы орталығы» немесе Профиль → «Токен шығару».
2. `.env`: `GOSZAKUP_TOKEN=<token>`
3. Base: `https://ows.goszakup.gov.kz`
4. Эндпоинттер: `GET /v3/trd-buy/all`, `GET /v3/trd-buy/{id}`

## Playwright stub (токенсіз)

Ашық порталды парсейді: [хабарландырулар іздеу](https://goszakup.gov.kz/ru/search/announce).

Әдепкі бойынша **аяқталған** сатып алуларды аламыз (өтінім қабылдау ашық емес):

- `filter[status][]=350` — хабарландыру мәртебесі «Аяқталды»;
- `filter[signs][]=is_not_active` — «Белсенді емес/аяқталған»;
- егжей-тегжейден кейін: шарт мәртебесі **Қолданыста** немесе **Орындалған** (соның ішінде «Передан.Действует» / «Передан.Исполнен»).

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
# GOSZAKUP_PW_OFFLINE=true   # тек fixtures HTML, браузерсіз
```

Скрапер әдепкі бойынша тек Маңғыстау облысын алады (`GOSZAKUP_PW_REGION_ONLY=mangystau`):

- порталдың негізгі сүзгісі `filter[kato]=470000000` (Маңғыстау облысының КАТО);
- тапсырыс беруші/топонимдер бойынша қосымша іздеу + мәтін бойынша пост-сүзгі;
- `map_kz_region` енді бөтен өңірлер үшін Маңғыстауды «әдепкі» етіп қоймайды.

```bash
# анық Playwright source
curl -X POST http://localhost:8000/api/v1/ingest/sources/KZ_GOSZAKUP_PLAYWRIGHT/run

# немесе сол OWS crawl — токен жоқ болса factory Playwright-қа ауысады
curl -X POST http://localhost:8000/api/v1/ingest/sources/KZ_GOSZAKUP_OWS_V3/run
```

Тексеру:

```bash
curl "http://localhost:8000/api/v1/tenders?source_code=KZ_GOSZAKUP_PLAYWRIGHT&country=KZ"
```

Парсер тесттері (offline):

```bash
pip install -e "packages/shared[playwright]" beautifulsoup4 lxml
pytest packages/shared/tests/test_goszakup_html.py -q
```

## Crawl іске қосу (жалпы)

```bash
docker compose up -d --build ingestion-worker
# Flower: http://localhost:5555
```
