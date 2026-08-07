**Тіл / Language:** [Русский](../ru/DATA_SOURCES.md) · [English](../en/DATA_SOURCES.md) · [Қазақша](DATA_SOURCES.md)

# Деректер көздері (Каспий алабы)

Мақсат: MVP және мемлекеттік масштабқа жарамдылығын бағалай отырып, **ашық** көздердің барынша кең каталогы.

Бағалау аңызы:
- **A** — тұрақты API / bulk download
- **B** — HTML/портал, парсинг реалистік
- **C** — ішінара ашық / тұрақсыз / заңдық шектеулер
- **D** — тек қолмен / ақылы / жабық

---

## 1. Мемлекеттік сатып алулар

| Көз | Ел | Тәсіл | Формат | Парсинг | Шектеулер | Grade |
|----------|--------|--------|--------|---------|-------------|-------|
| [goszakup.gov.kz](https://www.goszakup.gov.kz) + API/витриналар | KZ | REST (ресми API қолжетімді жерде) + HTML/Playwright | JSON / HTML | Жоғары | Captcha/rate-limit; API тіркеуі қажет; верстка өзгеруі | A/B |
| [zakup.sk.kz](https://zakup.sk.kz) (Самұрық-Қазына) | KZ | HTML / кейде XML | HTML | Орташа | Корп. сатып алулар ≠ мембюджет 100% | B |
| [etender.gov.az](https://etender.gov.az) | AZ | HTML + ықтимал API | HTML/JSON | Орташа | AZ/EN тілі; антибот | B |
| [zakupki.gov.ru](https://zakupki.gov.ru) (ЕИС) | RU | FTP/API EIS + HTML | XML/JSON | Жоғары (жетілген кітапханалар) | Көлем орасан; Каспий бойынша сүзгі (Астрахань, Дагестан, Қалмақия) | A |
| Түрікменстан мемлекеттік сатып алулары (мемпорталдар) | TM | HTML | HTML | Төмен | Шектеулі ашықтық, тұрақсыз URL | C/D |
| Иран тендер алаңдары (setad / жергілікті) | IR | HTML | HTML | Төмен–орташа | FA тілі; заңдық және санкциялық қолжетімділік шектеулері | C/D |
| World Bank / ADB project procurement notices | INT | API/RSS | JSON/XML | Жоғары | Барлық жобалар «эко-Каспий» емес; баға бенчмаркі ретінде жақсы | A |

**MVP-ұсыныс:** KZ goszakup (тереңдік) + RU EIS (өңірлер сүзгісі) **немесе** 50–100 эко-тендердің fixture-жиынтығы + 1 тірі парсер.

### Экологиялық кілт сөздер (сүзгі)

`очистка`, `нефтеразлив`, `берегоукрепление`, `дноуглубление`, `рекультивация`, `мониторинг воды`, `очистные`, `экология`, `Каспий`, `загрязнение`, `биоразнообразие`, `морской`, `порт`, `нефтеотходы`.

---

## 2. Нарықтық бағалар / прайс-парақтар

| Көз | Тәсіл | Формат | Парсинг | Шектеулер | Grade |
|----------|--------|--------|---------|-------------|-------|
| Ұлттық статистика комитеттері (құрылыс материалдары бағалары) | Bulk CSV/XLS | XLS/CSV | Жоғары | Агрегаттар, тендер unit-price емес | A |
| Құрылыс материалдары каталогтары (OLX/marketplaces — тек ашық беттер) | HTTP | HTML | Орташа | ToS, тұрақсыздық, шу | C |
| Мемлекеттік кәсіпорындар прайс-парақтары / прайс PDF | Download | PDF | Орташа | OCR/кестелер | B |
| Халықаралық индекстер (World Bank Pink Sheet, commodity) | API/CSV | CSV | Жоғары | Шикізат ≠ құрылыс жұмыстары | A |
| Сметалық нормативтер (ашық жарияланған жерде) | PDF/XLS | XLS | Орташа | Базаларға лицензиялар; IP-мен абай болу | B/C |
| Команданың эксперттік белгілеуі (seed prices) | Manual → CSV | CSV | — | Субъективтілік; cold start үшін міндетті | A (MVP үшін) |

**MVP:** `market_item` кестесі + 30–50 seed-баға (жер жұмыстары, геотекстиль, шламды шығару, судың зертханалық талдауы, бондық тосқауылдар).

---

## 3. Геодеректер және жағалау сызығы

| Көз | Тәсіл | Формат | Парсинг | Шектеулер | Grade |
|----------|--------|--------|---------|-------------|-------|
| OpenStreetMap (Overpass / Geofabrik Caspian extract) | Download PBF / Overpass QL | PBF/GeoJSON | Жоғары | ODbL attribution | A |
| Natural Earth coastline | Download | Shapefile | Жоғары | Масштаб 1:10m — дөрекі | A |
| GSHHG / coastline datasets | Download | Shapefile | Жоғары | Жағалау сызығы үшін | A |
| GADM / geoBoundaries (әкімш. шекаралар) | Download | GeoJSON | Жоғары | Лицензияларды тексеру | A |
| OpenAerialMap | API | tiles/meta | Орташа | Қамту біркелкі емес | B |
| UNEP-WCMC / WDPA (ЕҚТА) | Download | GPKG | Жоғары | Attribution | A |
| HydroBASINS / HydroSHEDS | Download | Shapefile | Жоғары | Су алаптары үшін | A |

**MVP:** Geofabrik extract + coastline polygon + Каспий маңы өңірлерінің әкімш. шекаралары.

---

## 4. Спутниктік деректер және ластанулар

| Көз | Тәсіл | Формат | Парсинг | Шектеулер | Grade |
|----------|--------|--------|---------|-------------|-------|
| Sentinel-2 (Copernicus Dataspace / GEE) | API / STAC | COG/JPEG2000 | Жоғары | Аккаунт қажет; көлем | A |
| Sentinel-1 SAR (мұнай төгілулері) | API | GeoTIFF | Жоғары | Оптикадан өңдеу күрделірек | A |
| NASA GIBS / Worldview | WMTS | tiles | Жоғары | UI үшін дайын тайлылар | A |
| NOAA / marine pollution reports | HTML/CSV | CSV | Орташа | Әрдайым Каспий емес | B |
| SkyTruth / ашық oil spill alerts (қолжетімді болса) | API/CSV | GeoJSON | Орташа | Қамту | B |
| Су сапасы — ұлттық гидрометқызметтер | PDF/HTML | tables | Төмен–орташа | Бөлінгендік | C |
| EMODnet / теңіз қабаттары (ішінара қолданылады) | WFS/WMS | GML | Орташа | Еуропаға фокус; Каспий шектеулі | C |

**MVP:** Leaflet base = OSM + overlay NASA GIBS; тендер маркерлері; мекенжай/порт геокодингінен жұмыс полигондары.  
Толыққанды oil-spill detection — **post-hackathon**.

---

## 5. Экологиялық базалар және тізілімдер

| Көз | Тәсіл | Формат | Шектеулер | Grade |
|----------|--------|--------|-------------|-------|
| Ластанулардың ұлттық кадастрлері / РПН аналогтары | HTML/PDF | tables | Елдер бойынша ашықтық деңгейі әртүрлі | B/C |
| CEP (Tehran Convention) ашық есептері | PDF | PDF | Машинамен оқылмайды | B |
| IUCN Red List (API) — жағалау биоалуантүрлілігі | API | JSON | Жанама белгі | A |
| GBIF occurrences | API | JSON | Ғылыми деректер | A |
| Climate TRACE / EDGAR emissions grids | Download | GeoTIFF | Дөрекі ажыратымдылық | A/B |
| Ұлттық EIA/ОВОС тізілімдері | HTML | HTML | Толық емес digitization | C |

---

## 6. Заңды тұлғалар / мердігерлер тізілімдері

| Көз | Тәсіл | Формат | Шектеулер | Grade |
|----------|--------|--------|-------------|-------|
| KZ: egov / stat.gov / заңды тұлғалардың ашық деректері | API/HTML | JSON | Өрістер әртүрлі | B |
| RU: ЕГРЮЛ ашық жүктемелер | Download | XML/CSV | Көлем | A |
| OpenCorporates | API | JSON | Rate limits / paid tiers | B |
| Санкциялық тізімдер (комплаенс үшін) | CSV/API | CSV | Заңдық сақтық | A |

Risk Score үшін маңызды: жеңістер саны, жалғыз өтінімдер үлесі, мекенжайлар/директорлар байланысы (graph — post-MVP).

---

## 7. Grade бойынша ingestion стратегиясы

```text
Grade A → connector (HTTP/STAC/FTP), schedule Celery Beat
Grade B → Playwright adapter + HTML fixtures regression tests
Grade C → manual CSV import + backlog ticket
Grade D → out of scope / legal review
```

Әр көз = `source` жазбасы + `SourceAdapter` + `crawl_job` метрикалары (success rate, latency).

---

## 8. Заңдық және этикалық шектеулер

1. Порталдар ToS-ын сақтау; prefer official API/open data.
2. CAPTCHA/auth-ты шабуыл ретінде айналып өтпеу; заңды кілттерді пайдалану.
3. Risk Score ≠ сыбайлас жемқорлықта айыптау; UI disclaimer міндетті.
4. Лауазымды тұлғалардың жеке деректері — public tier-де минимизация / маскалау.
5. OSM, Copernicus, Natural Earth үшін attribution — UI «Деректер туралы» бөлімінде.

---

## 9. 48 сағатқа басымдық

| # | Көз | Не үшін |
|---|----------|-------|
| 1 | Fixture JSON 80 Каспий эко-тендері | кепілденген демо |
| 2 | 1 тірі парсер (KZ немесе RU subset) | «жүйе парсей алады» |
| 3 | Seed market prices CSV | overprice feature |
| 4 | OSM coastline + regions GeoJSON | карта |
| 5 | NASA GIBS tiles | өз процессингсіз UI-дағы «спутник» |
| 6 | Статикалық eco layer (ЕҚТА / порттар) | жұмыстармен қиылысу |
