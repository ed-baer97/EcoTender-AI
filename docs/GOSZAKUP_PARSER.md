# Парсер goszakup.gov.kz (OWS v3)

Источник: [Унифицированные сервисы V3](https://goszakup.gov.kz/ru/developer/ows_v3)

## Что реализовано

| Компонент | Путь |
|-----------|------|
| `SourceAdapter` | `packages/shared/ecotender_shared/ingestion/goszakup_kz.py` |
| Eco-фильтр | `eco_filter.py` (ключевые слова + Каспий/Мангистау/Атырау) |
| Celery task | `app.workers.tasks.crawl_source` |
| Trigger API | `POST /api/v1/ingest/sources/KZ_GOSZAKUP_OWS_V3/run` |
| Upsert | `POST /v1/tenders/upsert` в tender-service |

## Auth

1. Получить токен у АО «Центр Электронных Финансов» или в профиле портала (роль Администратор) → «Выпуск токена».
2. В `.env`: `GOSZAKUP_TOKEN=<token>`
3. Заголовок: `Authorization: Bearer <token>`
4. Base URL: `https://ows.goszakup.gov.kz`

Без токена crawl идёт в режиме **sample_offline** по `data/fixtures/goszakup_sample.json`.

## Эндпоинты OWS, которые используем

- `GET /v3/trd-buy/all` — список объявлений (пагинация `next_page`)
- `GET /v3/trd-buy/{id}` — деталь объявления

Фильтрация eco/Caspian — на стороне адаптера (API не всегда удобно фильтрует по ключевым словам в REST).

## Запуск crawl

```bash
# поставить в очередь
curl -X POST http://localhost:8000/api/v1/ingest/sources/KZ_GOSZAKUP_OWS_V3/run

# статус задач — Flower
open http://localhost:5555

# проверить живые записи
curl "http://localhost:8000/api/v1/tenders?source_code=KZ_GOSZAKUP_OWS_V3&country=KZ"
```

Или напрямую Celery:

```bash
docker compose exec ingestion-worker celery -A app.workers.celery_app call app.workers.tasks.crawl_source --args='["KZ_GOSZAKUP_OWS_V3"]'
```
