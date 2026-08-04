# Источники данных (Каспийский бассейн)

Цель: максимально широкий каталог **открытых** источников с оценкой пригодности для MVP и гос. масштаба.

Легенда оценки:
- **A** — стабильный API / bulk download
- **B** — HTML/портал, парсинг реалистичен
- **C** — частично открыто / нестабильно / юр. ограничения
- **D** — только ручной / платный / закрытый

---

## 1. Государственные закупки

| Источник | Страна | Способ | Формат | Парсинг | Ограничения | Grade |
|----------|--------|--------|--------|---------|-------------|-------|
| [goszakup.gov.kz](https://www.goszakup.gov.kz) + API/витрины | KZ | REST (офиц. API где доступен) + HTML/Playwright | JSON / HTML | Высокая | Captcha/rate-limit; нужна регистрация API; смена вёрстки | A/B |
| [zakup.sk.kz](https://zakup.sk.kz) (Самрук-Казына) | KZ | HTML / иногда XML | HTML | Средняя | Корп. закупки ≠ госбюджет 100% | B |
| [etender.gov.az](https://etender.gov.az) | AZ | HTML + возможные API | HTML/JSON | Средняя | Язык AZ/EN; антибот | B |
| [zakupki.gov.ru](https://zakupki.gov.ru) (ЕИС) | RU | FTP/API EIS + HTML | XML/JSON | Высокая (зрелые библиотеки) | Объём огромный; фильтр по Каспию (Астрахань, Дагестан, Калмыкия) | A |
| Госзакупки Туркменистана (госпорталы) | TM | HTML | HTML | Низкая | Ограниченная открытость, нестабильные URL | C/D |
| Иранские тендерные площадки (setad / локальные) | IR | HTML | HTML | Низкая–средняя | Язык FA; юр. и санкционные ограничения доступа | C/D |
| World Bank / ADB project procurement notices | INT | API/RSS | JSON/XML | Высокая | Не все проекты «эко-Каспий»; хороши как бенчмарк цен | A |

**MVP-рекомендация:** KZ goszakup (глубина) + RU EIS (фильтр регионов) **или** fixture-набор 50–100 эко-тендеров + 1 живой парсер.

### Экологические ключевые слова (фильтр)

`очистка`, `нефтеразлив`, `берегоукрепление`, `дноуглубление`, `рекультивация`, `мониторинг воды`, `очистные`, `экология`, `Каспий`, `загрязнение`, `биоразнообразие`, `морской`, `порт`, `нефтеотходы`.

---

## 2. Рыночные цены / прайс-листы

| Источник | Способ | Формат | Парсинг | Ограничения | Grade |
|----------|--------|--------|---------|-------------|-------|
| Национальные стат. комитеты (цены на стройматериалы) | Bulk CSV/XLS | XLS/CSV | Высокая | Агрегаты, не unit-price тендера | A |
| Каталоги стройматериалов (OLX/marketplaces — только публичные страницы) | HTTP | HTML | Средняя | ToS, нестабильность, шум | C |
| Прайс-листы гос. предприятий / прайс PDF | Download | PDF | Средняя | OCR/таблицы | B |
| Международные индексы (World Bank Pink Sheet, commodity) | API/CSV | CSV | Высокая | Сырьё ≠ строительные работы | A |
| Сметные нормативы (где опубликованы открыто) | PDF/XLS | XLS | Средняя | Лицензии на базы; осторожно с IP | B/C |
| Экспертная разметка команды (seed prices) | Manual → CSV | CSV | — | Субъективность; обязательна для cold start | A (для MVP) |

**MVP:** таблица `market_item` + 30–50 seed-цен (земляные работы, геотекстиль, вывоз шлама, лабораторный анализ воды, боновые заграждения).

---

## 3. Геоданные и береговая линия

| Источник | Способ | Формат | Парсинг | Ограничения | Grade |
|----------|--------|--------|---------|-------------|-------|
| OpenStreetMap (Overpass / Geofabrik Caspian extract) | Download PBF / Overpass QL | PBF/GeoJSON | Высокая | ODbL attribution | A |
| Natural Earth coastline | Download | Shapefile | Высокая | Масштаб 1:10m — грубо | A |
| GSHHG / coastline datasets | Download | Shapefile | Высокая | Для береговой линии | A |
| GADM / geoBoundaries (адм. границы) | Download | GeoJSON | Высокая | Лицензии проверить | A |
| OpenAerialMap | API | tiles/meta | Средняя | Покрытие неравномерное | B |
| UNEP-WCMC / WDPA (ООПТ) | Download | GPKG | Высокая | Attribution | A |
| HydroBASINS / HydroSHEDS | Download | Shapefile | Высокая | Для водосборов | A |

**MVP:** Geofabrik extract + coastline polygon + адм. границы прикаспийских регионов.

---

## 4. Спутниковые данные и загрязнения

| Источник | Способ | Формат | Парсинг | Ограничения | Grade |
|----------|--------|--------|---------|-------------|-------|
| Sentinel-2 (Copernicus Dataspace / GEE) | API / STAC | COG/JPEG2000 | Высоняя | Нужен аккаунт; объём | A |
| Sentinel-1 SAR (разливы нефти) | API | GeoTIFF | Высокая | Обработка сложнее оптики | A |
| NASA GIBS / Worldview | WMTS | tiles | Высокая | Готовые тайлы для UI | A |
| NOAA / marine pollution reports | HTML/CSV | CSV | Средняя | Не всегда Каспий | B |
| SkyTruth / публичные oil spill alerts (если доступны) | API/CSV | GeoJSON | Средняя | Покрытие | B |
| Качество воды — национальные гидрометслужбы | PDF/HTML | tables | Низкая–средняя | Разрозненность | C |
| EMODnet / морские слои (частично применимо) | WFS/WMS | GML | Средняя | Фокус на Европе; Каспий ограничен | C |

**MVP:** Leaflet base = OSM + overlay NASA GIBS; маркеры тендеров; полигоны работ из геокодинга адреса/порта.  
Полноценный oil-spill detection — **post-hackathon**.

---

## 5. Экологические базы и реестры

| Источник | Способ | Формат | Ограничения | Grade |
|----------|--------|--------|-------------|-------|
| Национальные кадастры загрязнений / РПН аналоги | HTML/PDF | tables | Разный уровень открытости по странам | B/C |
| CEP (Tehran Convention) публичные отчёты | PDF | PDF | Не машиночитаемо | B |
| IUCN Red List (API) — биоразнообразие побережья | API | JSON | Косвенный признак | A |
| GBIF occurrences | API | JSON | Научные данные | A |
| Climate TRACE / EDGAR emissions grids | Download | GeoTIFF | Грубое разрешение | A/B |
| Национальные EIA/ОВОС реестры | HTML | HTML | Неполный digitization | C |

---

## 6. Реестры юрлиц / подрядчиков

| Источник | Способ | Формат | Ограничения | Grade |
|----------|--------|--------|-------------|-------|
| KZ: egov / stat.gov / открытые данные юрлиц | API/HTML | JSON | Поля различаются | B |
| RU: ЕГРЮЛ открытые выгрузки | Download | XML/CSV | Объём | A |
| OpenCorporates | API | JSON | Rate limits / paid tiers | B |
| Санкционные списки (для комплаенса) | CSV/API | CSV | Юр. осторожность | A |

Для Risk Score важны: число побед, доля единственных заявок, связанность адресов/директоров (graph — post-MVP).

---

## 7. Стратегия ingestion по грейдам

```text
Grade A → connector (HTTP/STAC/FTP), schedule Celery Beat
Grade B → Playwright adapter + HTML fixtures regression tests
Grade C → manual CSV import + backlog ticket
Grade D → out of scope / legal review
```

Каждый источник = запись в `source` + `SourceAdapter` + `crawl_job` метрики (success rate, latency).

---

## 8. Юридические и этические ограничения

1. Соблюдать ToS порталов; prefer official API/open data.
2. Не обходить CAPTCHA/auth как атаку; использовать легальные ключи.
3. Risk Score ≠ обвинение в коррупции; UI disclaimer обязателен.
4. Персональные данные должностных лиц — минимизация / маскирование в public tier.
5. Attribution для OSM, Copernicus, Natural Earth — в UI «О данных».

---

## 9. Приоритет для 48 часов

| # | Источник | Зачем |
|---|----------|-------|
| 1 | Fixture JSON 80 эко-тендеров Каспия | гарантированное демо |
| 2 | 1 живой парсер (KZ или RU subset) | «система умеет парсить» |
| 3 | Seed market prices CSV | overprice feature |
| 4 | OSM coastline + regions GeoJSON | карта |
| 5 | NASA GIBS tiles | «спутник» в UI без своего процессинга |
| 6 | Статический eco layer (ООПТ / порты) | пересечение с работами |
