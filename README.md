# EcoTender AI

**Язык / Language / Тіл:** [Русский](README.ru.md) · [English](README.en.md) · [Қазақша](README.kk.md)

Интеллектуальная платформа прозрачности экологических тендеров Каспийского моря  
**Caspian Hackathon 2026** · «Caspian Sea Action Week»  
**Команда:** IT LYCEUM Team

| | |
|--|--|
| Документация | [docs/](docs/README.md) — RU / EN / KK |
| Описание проекта | [docs/ru/PROJECT_DESCRIPTION.md](docs/ru/PROJECT_DESCRIPTION.md) |
| Авторы | [AUTHORS.md](AUTHORS.md) |
| GitHub | https://github.com/ed-baer97/EcoTender-AI |

## Быстрый старт

```bash
git clone https://github.com/ed-baer97/EcoTender-AI.git
cd EcoTender-AI
cp .env.example .env
docker compose up -d --build
python scripts/smoke_check.py
```

| Сервис | URL |
|--------|-----|
| Web UI | http://localhost:5173 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |

Тестовые логины: `admin@ecotender.kz` / `admin123` · `analyst@ecotender.kz` / `analyst123`

Полная инструкция: [README.ru.md](README.ru.md) · [README.en.md](README.en.md) · [README.kk.md](README.kk.md)
