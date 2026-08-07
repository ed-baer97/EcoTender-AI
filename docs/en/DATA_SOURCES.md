**Language:** [Русский](../ru/DATA_SOURCES.md) · [English](DATA_SOURCES.md) · [Қазақша](../kk/DATA_SOURCES.md)

# Data Sources (Caspian Basin)

Goal: the broadest possible catalog of **open** sources with a fitness assessment for MVP and national scale.

Grade legend:
- **A** — stable API / bulk download
- **B** — HTML/portal, parsing is realistic
- **C** — partially open / unstable / legal restrictions
- **D** — manual only / paid / closed

---

## 1. Public Procurement

| Source | Country | Method | Format | Parsing | Constraints | Grade |
|--------|---------|--------|--------|---------|-------------|-------|
| [goszakup.gov.kz](https://www.goszakup.gov.kz) + API/vitrines | KZ | REST (official API where available) + HTML/Playwright | JSON / HTML | High | Captcha/rate-limit; API registration needed; layout changes | A/B |
| [zakup.sk.kz](https://zakup.sk.kz) (Samruk-Kazyna) | KZ | HTML / sometimes XML | HTML | Medium | Corporate procurements ≠ 100% state budget | B |
| [etender.gov.az](https://etender.gov.az) | AZ | HTML + possible APIs | HTML/JSON | Medium | Language AZ/EN; anti-bot | B |
| [zakupki.gov.ru](https://zakupki.gov.ru) (EIS) | RU | FTP/API EIS + HTML | XML/JSON | High (mature libraries) | Huge volume; filter by Caspian (Astrakhan, Dagestan, Kalmykia) | A |
| Turkmenistan public procurement (state portals) | TM | HTML | HTML | Low | Limited openness, unstable URLs | C/D |
| Iranian tender platforms (setad / local) | IR | HTML | HTML | Low–medium | Language FA; legal and sanctions access limits | C/D |
| World Bank / ADB project procurement notices | INT | API/RSS | JSON/XML | High | Not all projects are “eco-Caspian”; good as price benchmarks | A |

**MVP recommendation:** KZ goszakup (depth) + RU EIS (region filter) **or** a fixture set of 50–100 eco-tenders + 1 live parser.

### Environmental Keywords (Filter)

`очистка`, `нефтеразлив`, `берегоукрепление`, `дноуглубление`, `рекультивация`, `мониторинг воды`, `очистные`, `экология`, `Каспий`, `загрязнение`, `биоразнообразие`, `морской`, `порт`, `нефтеотходы`.

---

## 2. Market Prices / Price Lists

| Source | Method | Format | Parsing | Constraints | Grade |
|--------|--------|--------|---------|-------------|-------|
| National statistical committees (construction material prices) | Bulk CSV/XLS | XLS/CSV | High | Aggregates, not tender unit-price | A |
| Construction material catalogs (OLX/marketplaces — public pages only) | HTTP | HTML | Medium | ToS, instability, noise | C |
| Price lists of state enterprises / price PDFs | Download | PDF | Medium | OCR/tables | B |
| International indices (World Bank Pink Sheet, commodity) | API/CSV | CSV | High | Commodities ≠ construction works | A |
| Estimate norms (where published openly) | PDF/XLS | XLS | Medium | Database licenses; careful with IP | B/C |
| Team expert labeling (seed prices) | Manual → CSV | CSV | — | Subjectivity; required for cold start | A (for MVP) |

**MVP:** `market_item` table + 30–50 seed prices (earthworks, geotextile, sludge removal, water lab analysis, boom barriers).

---

## 3. Geodata and Coastline

| Source | Method | Format | Parsing | Constraints | Grade |
|--------|--------|--------|---------|-------------|-------|
| OpenStreetMap (Overpass / Geofabrik Caspian extract) | Download PBF / Overpass QL | PBF/GeoJSON | High | ODbL attribution | A |
| Natural Earth coastline | Download | Shapefile | High | Scale 1:10m — coarse | A |
| GSHHG / coastline datasets | Download | Shapefile | High | For coastline | A |
| GADM / geoBoundaries (admin boundaries) | Download | GeoJSON | High | Check licenses | A |
| OpenAerialMap | API | tiles/meta | Medium | Uneven coverage | B |
| UNEP-WCMC / WDPA (protected areas) | Download | GPKG | High | Attribution | A |
| HydroBASINS / HydroSHEDS | Download | Shapefile | High | For watersheds | A |

**MVP:** Geofabrik extract + coastline polygon + admin boundaries of Caspian littoral regions.

---

## 4. Satellite Data and Pollution

| Source | Method | Format | Parsing | Constraints | Grade |
|--------|--------|--------|---------|-------------|-------|
| Sentinel-2 (Copernicus Dataspace / GEE) | API / STAC | COG/JPEG2000 | High | Account needed; volume | A |
| Sentinel-1 SAR (oil spills) | API | GeoTIFF | High | Processing harder than optical | A |
| NASA GIBS / Worldview | WMTS | tiles | High | Ready tiles for UI | A |
| NOAA / marine pollution reports | HTML/CSV | CSV | Medium | Not always Caspian | B |
| SkyTruth / public oil spill alerts (if available) | API/CSV | GeoJSON | Medium | Coverage | B |
| Water quality — national hydromet services | PDF/HTML | tables | Low–medium | Fragmentation | C |
| EMODnet / marine layers (partially applicable) | WFS/WMS | GML | Medium | Europe focus; Caspian limited | C |

**MVP:** Leaflet base = OSM + NASA GIBS overlay; tender markers; work polygons from address/port geocoding.  
Full oil-spill detection — **post-hackathon**.

---

## 5. Environmental Databases and Registries

| Source | Method | Format | Constraints | Grade |
|--------|--------|--------|-------------|-------|
| National pollution cadastres / RPN analogs | HTML/PDF | tables | Varying openness by country | B/C |
| CEP (Tehran Convention) public reports | PDF | PDF | Not machine-readable | B |
| IUCN Red List (API) — coastal biodiversity | API | JSON | Indirect feature | A |
| GBIF occurrences | API | JSON | Scientific data | A |
| Climate TRACE / EDGAR emissions grids | Download | GeoTIFF | Coarse resolution | A/B |
| National EIA/OVOS registries | HTML | HTML | Incomplete digitization | C |

---

## 6. Legal Entity / Contractor Registries

| Source | Method | Format | Constraints | Grade |
|--------|--------|--------|-------------|-------|
| KZ: egov / stat.gov / open legal-entity data | API/HTML | JSON | Fields differ | B |
| RU: EGRUL open dumps | Download | XML/CSV | Volume | A |
| OpenCorporates | API | JSON | Rate limits / paid tiers | B |
| Sanctions lists (for compliance) | CSV/API | CSV | Legal caution | A |

For Risk Score the important signals are: win count, share of single bids, address/director linkage (graph — post-MVP).

---

## 7. Ingestion Strategy by Grade

```text
Grade A → connector (HTTP/STAC/FTP), schedule Celery Beat
Grade B → Playwright adapter + HTML fixtures regression tests
Grade C → manual CSV import + backlog ticket
Grade D → out of scope / legal review
```

Each source = a `source` record + `SourceAdapter` + `crawl_job` metrics (success rate, latency).

---

## 8. Legal and Ethical Constraints

1. Respect portal ToS; prefer official API/open data.
2. Do not bypass CAPTCHA/auth as an attack; use legal keys.
3. Risk Score ≠ accusation of corruption; UI disclaimer is mandatory.
4. Personal data of officials — minimization / masking in public tier.
5. Attribution for OSM, Copernicus, Natural Earth — in UI “About data”.

---

## 9. Priority for 48 Hours

| # | Source | Why |
|---|--------|-----|
| 1 | Fixture JSON 80 Caspian eco-tenders | guaranteed demo |
| 2 | 1 live parser (KZ or RU subset) | “the system can parse” |
| 3 | Seed market prices CSV | overprice feature |
| 4 | OSM coastline + regions GeoJSON | map |
| 5 | NASA GIBS tiles | “satellite” in UI without own processing |
| 6 | Static eco layer (protected areas / ports) | intersection with works |
