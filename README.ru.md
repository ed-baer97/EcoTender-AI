# EcoTender AI

**Язык / Language / Тіл:** [Русский](README.ru.md) · [English](README.en.md) · [Қазақша](README.kk.md)

Интеллектуальная платформа прозрачности экологических тендеров Каспийского моря  
**Caspian Hackathon 2026** · Международная неделя действий «Caspian Sea Action Week»

> AI + GIS + открытые закупки: Risk Score эко-тендеров для госорганов, аудиторов и общественного контроля.  
> MVP на Docker Compose; каркас масштабируется до государственной платформы.

**GitHub:** https://github.com/ed-baer97/EcoTender-AI  
**Авторы:** [AUTHORS.md](AUTHORS.md)  
**Описание проекта:** [docs/ru/PROJECT_DESCRIPTION.md](docs/ru/PROJECT_DESCRIPTION.md)  
**Документация:** [docs/README.md](docs/README.md)

---

## Краткое описание

EcoTender AI собирает экологически релевантные госзакупки (Казахстан / Каспий), сравнивает цены с рынком, показывает объекты на карте (PostGIS + Leaflet) и считает **Risk Score 0–100** моделью CatBoost с текстовым объяснением для аудитора (LLM API или шаблон без ключа).

Фокус: прозрачность средств на сохранение Каспийского моря + геоинформационный мониторинг эко-проектов.

## Основные функции

1. **Каталог эко-тендеров** — список, фильтры, карточка закупки (fixtures / goszakup).
2. **Карта рисков** — маркеры по уровню риска, слои ООПТ / NASA GIBS (demo).
3. **Risk Score** — CatBoost 0–100, bands low → critical.
4. **Explain** — причины оценки (LLM или template fallback).
5. **Рыночное сравнение** — отклонение цены от ориентира.
6. **Ingestion** — парсер goszakup (OWS v3 / Playwright), Celery + Flower.
7. **Кабинет администратора** — ключи LLM/парсеров с шифрованием at rest.
8. **Auth (demo)** — JWT, роли viewer / analyst / admin.

Подробнее: [docs/ru/PROJECT_DESCRIPTION.md](docs/ru/PROJECT_DESCRIPTION.md).

---

## Минимальные системные требования

| Ресурс | Минимум |
|--------|---------|
| ОС | Windows 10/11, macOS 12+, Linux (x86_64) |
| CPU / RAM | 4 vCPU · **8 GB RAM** (рекомендуется 16 GB) |
| Диск | ~10 GB свободно (образы Docker) |
| Сеть | Для сборки образов; офлайн-демо работает на fixtures |

## Необходимые программные компоненты

- [Docker](https://docs.docker.com/get-docker/) **24+** и Docker Compose v2  
- (Опционально) Python **3.11+** — только для `scripts/smoke_check.py` с хоста  
- (Опционально) Git — клонирование репозитория  
- Браузер: Chrome / Edge / Firefox актуальной версии  

LLM-ключ **не обязателен**: без него работает template explain. Ключ goszakup OWS — опционален (есть Playwright-stub и fixtures).

---

## Установка

```bash
git clone https://github.com/ed-baer97/EcoTender-AI.git
cd EcoTender-AI
cp .env.example .env
```

При необходимости отредактируйте `.env` (пароли Postgres/MinIO, `JWT_SECRET`). Для демо достаточно значений из примера.

## Запуск

```bash
docker compose up -d --build
```

Дождитесь healthy-статуса контейнеров (первый запуск — несколько минут).

Проверка:

```bash
python scripts/smoke_check.py
```

Ожидаемый итог: `SMOKE OK`.

| Сервис | URL |
|--------|-----|
| Web UI | http://localhost:5173 |
| API Gateway | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Flower (Celery) | http://localhost:5555 |
| MinIO Console | http://localhost:9101 |

Остановка: `docker compose down`.

## Данные для входа (тестовые учётные записи)

| Роль | Email | Пароль |
|------|-------|--------|
| Администратор | `admin@ecotender.kz` | `admin123` |
| Аналитик | `analyst@ecotender.kz` | `analyst123` |

Кабинет ключей LLM / парсеров: войти как admin → **Кабинет администратора**.  
Ключи at rest шифруются Fernet (`SECRET_ENCRYPTION_KEY` / fallback `JWT_SECRET`), в Redis/file — префикс `enc:v1:`.

---

## Структура проекта

```
apps/web                 # React SPA — карта, каталог, кабинет
services/
  api-gateway            # BFF / auth / rate-limit
  tender-service         # тендеры, контракты, участники
  market-service         # рыночные цены
  geo-service            # PostGIS, слои, снимки
  risk-engine            # CatBoost + anomaly + LLM explain
  ingestion-workers      # парсеры + Celery
packages/shared          # pydantic schemas, SourceAdapter, secrets
ml/                      # обучение CatBoost, models/
data/fixtures            # демо-тендеры и HTML-фикстуры
infra/                   # postgres init, nginx/otel stubs
docs/ru|en|kk            # документация на 3 языках
scripts/                 # smoke_check и утилиты
```

Полный разбор сервисов: [docs/ru/ARCHITECTURE.md](docs/ru/ARCHITECTURE.md).

---

## Стек

**Backend:** FastAPI · SQLAlchemy 2 · Alembic · Celery · Redis 8 · PostgreSQL 17 + PostGIS 3.5  
**Frontend:** React 19 · TypeScript · Vite 6 · MUI 7 · Leaflet / react-leaflet 5  
**Ingestion:** Playwright · BeautifulSoup · lxml  
**AI:** CatBoost (свой score) + LLM API (gpt-5.6-terra / DeepSeek / Qwen 3.8 Max) · template fallback  
**GIS:** PostGIS 3.5 · GeoPandas · Shapely · Leaflet  

Версии: [docs/ru/STACK.md](docs/ru/STACK.md). Зависимости Python — `packages/shared/pyproject.toml` и `requirements` сервисов; фронт — `apps/web/package.json`.

## Документация

| Документ | RU | EN | KK |
|----------|----|----|-----|
| Описание проекта | [ru](docs/ru/PROJECT_DESCRIPTION.md) | [en](docs/en/PROJECT_DESCRIPTION.md) | [kk](docs/kk/PROJECT_DESCRIPTION.md) |
| Архитектура | [ru](docs/ru/ARCHITECTURE.md) | [en](docs/en/ARCHITECTURE.md) | [kk](docs/kk/ARCHITECTURE.md) |
| API | [ru](docs/ru/API.md) | [en](docs/en/API.md) | [kk](docs/kk/API.md) |
| Risk Engine | [ru](docs/ru/ML_RISK_ENGINE.md) | [en](docs/en/ML_RISK_ENGINE.md) | [kk](docs/kk/ML_RISK_ENGINE.md) |
| Источники данных | [ru](docs/ru/DATA_SOURCES.md) | [en](docs/en/DATA_SOURCES.md) | [kk](docs/kk/DATA_SOURCES.md) |
| ER-модель | [ru](docs/ru/ER_DIAGRAM.md) | [en](docs/en/ER_DIAGRAM.md) | [kk](docs/kk/ER_DIAGRAM.md) |
| goszakup | [ru](docs/ru/GOSZAKUP_PARSER.md) | [en](docs/en/GOSZAKUP_PARSER.md) | [kk](docs/kk/GOSZAKUP_PARSER.md) |
| Стек | [ru](docs/ru/STACK.md) | [en](docs/en/STACK.md) | [kk](docs/kk/STACK.md) |
| Масштабирование | [ru](docs/ru/SCALING.md) | [en](docs/en/SCALING.md) | [kk](docs/kk/SCALING.md) |

Индекс: [docs/README.md](docs/README.md).

## Лицензия и сторонние компоненты

MIT — хакатон / open source demo. Для продакшена гос. контура — отдельное соглашение.

Используются open-source библиотеки и публичные API (см. стек выше) на условиях их лицензий. Risk Score — аналитический сигнал, не юридическое обвинение.
