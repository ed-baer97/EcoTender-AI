# EcoTender AI

**Тіл / Language:** [Русский](README.ru.md) · [English](README.en.md) · [Қазақша](README.kk.md)

Каспий теңізінің экологиялық тендерлерін ашық етудеуге арналған зияткерлік платформа  
**Caspian Hackathon 2026** · «Caspian Sea Action Week»

> AI + GIS + ашық сатып алу: мемлекеттік органдар, аудиторлар және қоғамдық бақылау үшін эко-тендерлердің Risk Score.  
> Docker Compose MVP; мемлекеттік платформаға дейін масштабталады.

**GitHub:** https://github.com/ed-baer97/EcoTender-AI  
**Авторлар:** [AUTHORS.md](AUTHORS.md)  
**Жоба сипаттамасы:** [docs/kk/PROJECT_DESCRIPTION.md](docs/kk/PROJECT_DESCRIPTION.md)  
**Құжаттама:** [docs/README.md](docs/README.md)

---

## Қысқаша сипаттама

EcoTender AI экологиялық маңызы бар мемлекеттік сатып алуларды (Қазақстан / Каспий) жинайды, бағаларды нарықпен салыстырады, нысандарды картада көрсетеді (PostGIS + Leaflet) және CatBoost моделімен **Risk Score 0–100** есептейді, аудиторға мәтіндік түсініктеме береді (LLM API немесе кілтсіз шаблон).

Бағыт: Каспийді сақтауға бөлінген қаражаттың ашықтығы + эко-жобалардың геомониторингі.

## Негізгі функциялар

1. **Эко-тендерлер каталогы** — тізім, сүзгілер, карточка (fixtures / goszakup).
2. **Тәуекел картасы** — тәуекел деңгейі бойынша маркерлер, ЕҚТА / NASA GIBS (demo).
3. **Risk Score** — CatBoost 0–100, bands low → critical.
4. **Explain** — бағалау себептері (LLM немесе template fallback).
5. **Нарықтық салыстыру** — бағаның бағдардан ауытқуы.
6. **Ingestion** — goszakup парсері (OWS v3 / Playwright), Celery + Flower.
7. **Әкімші кабинеті** — LLM/парсер кілттері шифрланған түрде.
8. **Auth (demo)** — JWT, рөлдер viewer / analyst / admin.

Толығырақ: [docs/kk/PROJECT_DESCRIPTION.md](docs/kk/PROJECT_DESCRIPTION.md).

---

## Минималды жүйелік талаптар

| Ресурс | Минимум |
|--------|---------|
| ОС | Windows 10/11, macOS 12+, Linux (x86_64) |
| CPU / RAM | 4 vCPU · **8 GB RAM** (16 GB ұсынылады) |
| Диск | ~10 GB бос орын (Docker образдар) |
| Желі | Образ жинау үшін; офлайн-демо fixtures-пен жұмыс істейді |

## Қажетті бағдарламалық компоненттер

- [Docker](https://docs.docker.com/get-docker/) **24+** және Docker Compose v2  
- (Қосымша) Python **3.11+** — тек хосттағы `scripts/smoke_check.py` үшін  
- (Қосымша) Git — репозиторийді клондау  
- Браузер: Chrome / Edge / Firefox  

LLM кілті **міндетті емес**. goszakup OWS токені де қосымша (Playwright-stub және fixtures бар).

---

## Орнату

```bash
git clone https://github.com/ed-baer97/EcoTender-AI.git
cd EcoTender-AI
cp .env.example .env
```

Қажет болса `.env` өңдеңіз. Демо үшін мысал мәндері жеткілікті.

## Іске қосу

```bash
docker compose up -d --build
```

Контейнерлер healthy болғанша күтіңіз (алғашқы іске қосу бірнеше минут алуы мүмкін).

Тексеру:

```bash
python scripts/smoke_check.py
```

Күтілетін нәтиже: `SMOKE OK`.

| Сервис | URL |
|--------|-----|
| Web UI | http://localhost:5173 |
| API Gateway | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Flower (Celery) | http://localhost:5555 |
| MinIO Console | http://localhost:9101 |

Тоқтату: `docker compose down`.

## Кіру деректері (тесттік есептік жазбалар)

| Рөл | Email | Құпиясөз |
|-----|-------|----------|
| Әкімші | `admin@ecotender.kz` | `admin123` |
| Аналитик | `analyst@ecotender.kz` | `analyst123` |

LLM/парсер кілттері: admin болып кіріңіз → **Әкімші кабинеті**.  
Кілттер Fernet-пен шифрланады (`SECRET_ENCRYPTION_KEY` / fallback `JWT_SECRET`), префикс `enc:v1:`.

---

## Жоба құрылымы

```
apps/web                 # React SPA — карта, каталог, кабинет
services/
  api-gateway            # BFF / auth / rate-limit
  tender-service         # тендерлер, келісімшарттар
  market-service         # нарықтық бағалар
  geo-service            # PostGIS, қабаттар
  risk-engine            # CatBoost + anomaly + LLM explain
  ingestion-workers      # парсерлер + Celery
packages/shared          # schemas, SourceAdapter, secrets
ml/                      # CatBoost оқыту, models/
data/fixtures            # демо-тендерлер
infra/                   # postgres init
docs/ru|en|kk            # құжаттама 3 тілде
scripts/                 # smoke_check
```

Архитектура: [docs/kk/ARCHITECTURE.md](docs/kk/ARCHITECTURE.md).

---

## Стек

**Backend:** FastAPI · SQLAlchemy 2 · Alembic · Celery · Redis 8 · PostgreSQL 17 + PostGIS 3.5  
**Frontend:** React 19 · TypeScript · Vite 6 · MUI 7 · Leaflet  
**Ingestion:** Playwright · BeautifulSoup · lxml  
**AI:** CatBoost + LLM API · template fallback  
**GIS:** PostGIS 3.5 · GeoPandas · Shapely · Leaflet  

Нұсқалар: [docs/kk/STACK.md](docs/kk/STACK.md).

## Құжаттама

| Құжат | RU | EN | KK |
|-------|----|----|-----|
| Жоба сипаттамасы | [ru](docs/ru/PROJECT_DESCRIPTION.md) | [en](docs/en/PROJECT_DESCRIPTION.md) | [kk](docs/kk/PROJECT_DESCRIPTION.md) |
| Архитектура | [ru](docs/ru/ARCHITECTURE.md) | [en](docs/en/ARCHITECTURE.md) | [kk](docs/kk/ARCHITECTURE.md) |
| API | [ru](docs/ru/API.md) | [en](docs/en/API.md) | [kk](docs/kk/API.md) |
| Risk Engine | [ru](docs/ru/ML_RISK_ENGINE.md) | [en](docs/en/ML_RISK_ENGINE.md) | [kk](docs/kk/ML_RISK_ENGINE.md) |
| Дерек көздері | [ru](docs/ru/DATA_SOURCES.md) | [en](docs/en/DATA_SOURCES.md) | [kk](docs/kk/DATA_SOURCES.md) |
| ER-модель | [ru](docs/ru/ER_DIAGRAM.md) | [en](docs/en/ER_DIAGRAM.md) | [kk](docs/kk/ER_DIAGRAM.md) |
| goszakup | [ru](docs/ru/GOSZAKUP_PARSER.md) | [en](docs/en/GOSZAKUP_PARSER.md) | [kk](docs/kk/GOSZAKUP_PARSER.md) |
| Стек | [ru](docs/ru/STACK.md) | [en](docs/en/STACK.md) | [kk](docs/kk/STACK.md) |
| Масштабтау | [ru](docs/ru/SCALING.md) | [en](docs/en/SCALING.md) | [kk](docs/kk/SCALING.md) |

## Лицензия

MIT — хакатон / open source demo. Өндірістік мемлекеттік контур үшін жеке келісім қажет.

Risk Score — аналитикалық сигнал, заңды айыптау емес.
