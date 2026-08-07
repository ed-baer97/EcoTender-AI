**Язык / Language / Тіл:** [Русский](GOSZAKUP_PARSER.md) · [English](../en/GOSZAKUP_PARSER.md) · [Қазақша](../kk/GOSZAKUP_PARSER.md)

# Парсер goszakup.gov.kz

## Режимы ingestion

| Режим | Когда | `source_code` | `mode` в ответе crawl |
|-------|--------|---------------|------------------------|
| **OWS v3 API** | есть `GOSZAKUP_TOKEN` | `KZ_GOSZAKUP_OWS_V3` | `live_api` |
| **Playwright stub** | нет токена, `GOSZAKUP_USE_PLAYWRIGHT=true` | `KZ_GOSZAKUP_PLAYWRIGHT` или тот же OWS code | `playwright_stub` |
| **Offline sample** | нет токена, Playwright выключен | `KZ_GOSZAKUP_OWS_V3` | `sample_offline` |

Документация API: [OWS v3](https://goszakup.gov.kz/ru/developer/ows_v3) · [OWS v2](https://goszakup.gov.kz/ru/developer/ows_v2)

## Что реализовано

| Компонент | Путь |
|-----------|------|
| OWS adapter | `packages/shared/ecotender_shared/ingestion/goszakup_kz.py` |
| Playwright stub | `packages/shared/ecotender_shared/ingestion/goszakup_playwright.py` |
| HTML parser | `packages/shared/ecotender_shared/ingestion/goszakup_html.py` |
| Factory (выбор режима) | `packages/shared/ecotender_shared/ingestion/goszakup_factory.py` |
| Eco-фильтр | `eco_filter.py` |
| Celery task | `app.workers.tasks.crawl_source` |
| HTML fixtures (тесты / offline) | `data/fixtures/html/` |

## OWS v3 (production)

1. Токен: АО «Центр Электронных Финансов» или Профиль → «Выпуск токена».
2. `.env`: `GOSZAKUP_TOKEN=<token>`
3. Base: `https://ows.goszakup.gov.kz`
4. Эндпоинты: `GET /v3/trd-buy/all`, `GET /v3/trd-buy/{id}`

## Playwright stub (без токена)

Парсит публичный портал: [поиск объявлений](https://goszakup.gov.kz/ru/search/announce).

По умолчанию берём **завершённые** закупки (не открытый приём заявок):

- `filter[status][]=350` — статус объявления «Завершено»;
- `filter[signs][]=is_not_active` — «Неактивные/завершенные»;
- после детализации: договор в статусе **Действует** или **Исполнен** (в т.ч. «Передан.Действует» / «Передан.Исполнен»).

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
# GOSZAKUP_PW_OFFLINE=true   # только fixtures HTML, без браузера
```

Скрапер по умолчанию берёт только Мангистаускую область (`GOSZAKUP_PW_REGION_ONLY=mangystau`):

- основной фильтр портала `filter[kato]=470000000` (КАТО Мангистауской области);
- доп. поиск по заказчику/топонимам + пост-фильтр по тексту;
- `map_kz_region` больше не подставляет Мангистау «по умолчанию» для чужих регионов.

```bash
# явный source Playwright
curl -X POST http://localhost:8000/api/v1/ingest/sources/KZ_GOSZAKUP_PLAYWRIGHT/run

# или тот же crawl OWS — factory переключится на Playwright, если нет токена
curl -X POST http://localhost:8000/api/v1/ingest/sources/KZ_GOSZAKUP_OWS_V3/run
```

Проверка:

```bash
curl "http://localhost:8000/api/v1/tenders?source_code=KZ_GOSZAKUP_PLAYWRIGHT&country=KZ"
```

Тесты парсера (offline):

```bash
pip install -e "packages/shared[playwright]" beautifulsoup4 lxml
pytest packages/shared/tests/test_goszakup_html.py -q
```

## Запуск crawl (общее)

```bash
docker compose up -d --build ingestion-worker
# Flower: http://localhost:5555
```
