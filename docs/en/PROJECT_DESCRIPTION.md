**Language:** [Русский](../ru/PROJECT_DESCRIPTION.md) · [English](PROJECT_DESCRIPTION.md) · [Қазақша](../kk/PROJECT_DESCRIPTION.md)

# Project Description — EcoTender AI

Caspian Hackathon 2026 · transparency platform for environmental tenders of the Caspian Sea.

## Environmental Problem

The Caspian Sea is the world’s largest enclosed body of water. Its ecosystem is under pressure from oil and waste pollution, coastal degradation, declining biological resources, and **insufficient digitalization of environmental monitoring**.

A separate systemic risk: funds allocated to protect and restore the Caspian (state budget, grants, eco-tenders) are spent **opaquely**. Inflated prices, single-bidder procurements, repeated wins by the same contractors, and procedural anomalies reduce the real environmental impact of projects.

## Relevance

An AI platform is needed for transparency and efficient use of funds for Caspian Sea conservation: spending monitoring, corruption-risk detection, and control of eco-project delivery.

Without automated procurement analysis, oversight bodies and NGOs must manually review notices on goszakup and similar portals. Data is fragmented; GIS context (protected areas, coastline) is rarely linked to the financial side. EcoTender AI closes that gap: **procurement + market + geography + AI risk** in one loop.

## Proposed Solution

**EcoTender AI** is a web platform (information system + AI + GIS) that:

1. collects environmentally relevant tenders (fixtures / goszakup OWS v3 / Playwright);
2. compares prices with market benchmarks;
3. overlays objects on a Caspian map (PostGIS, Leaflet, protected-area / NASA GIBS layers);
4. computes a **Risk Score 0–100** with its own CatBoost model;
5. explains the score to the auditor via an LLM API or a template fallback (no key).

Format: web application / digital platform / AI solution / data analysis system / GIS service.

## Core Product Features

| Feature | What the user sees |
|---------|---------------------|
| Eco-tender catalog | List, filters by country/risk, procurement card |
| Interactive map | Markers by risk level, Caspian/KZ bbox |
| Risk Score | Number 0–100 and band: low / medium / high / critical |
| Explain | Text rationale (verdict, reasons, confidence) |
| Market comparison | Price deviation from seed/market estimate |
| GIS layers | Protected areas, work polygons, NASA GIBS (demo) |
| Ingestion | goszakup parsing, Celery/Flower, demo fixtures |
| Admin cabinet | LLM/parser keys (encryption at rest), source management |
| Auth (demo) | Roles viewer / analyst / admin, JWT |

## Technologies Used

- **Backend:** FastAPI, SQLAlchemy 2, Alembic, Celery, Redis
- **Data:** PostgreSQL 17 + PostGIS 3.5, MinIO
- **Frontend:** React 19, TypeScript, Vite, MUI, Leaflet
- **AI/ML:** CatBoost (decision), OpenAI-compatible LLM API (explanation)
- **Ingestion:** Playwright, BeautifulSoup, lxml; `SourceAdapter` adapter
- **Infra:** Docker Compose

Details: [STACK.md](STACK.md), [ARCHITECTURE.md](ARCHITECTURE.md), [ML_RISK_ENGINE.md](ML_RISK_ENGINE.md).

## Expected Environmental Impact

- Early detection of risky eco-procurements → higher chance that budget reaches real cleanup/monitoring/reclamation.
- “Money ↔ territory” link (map + protected areas) → oversight priority where ecosystem damage is higher.
- Transparency for government bodies, auditors, and the public → greater trust in Caspian conservation programs.
- Scaling across Caspian countries via source adapters (KZ → AZ/RU/…).

*Product disclaimer:* Risk Score is an analytical signal, not a legal accusation.

## Intended Users

| Audience | Scenario |
|----------|----------|
| Government / anti-corruption / Supreme Audit | Selecting procurements for review |
| Ministry of Ecology / regional agencies | Monitoring Caspian eco-projects |
| Scientific organizations and NGOs | Public environmental oversight |
| Banks / insurers of eco-projects | Contractor due diligence |
| Public / journalists | Public risk map (open core) |

## Development Prospects

See [SCALING.md](SCALING.md):

1. **Pilot** — one agency, parsing SLA, methodology whitepaper  
2. **Multi-country Caspian** — AZ/RU/TM/IR adapters, i18n  
3. **National platform** — Kafka, feature store, Sentinel/oil spill, SSO, open data portal  
