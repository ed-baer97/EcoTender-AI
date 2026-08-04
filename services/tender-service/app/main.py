"""FastAPI tender-service backed by PostgreSQL + PostGIS."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, get_session
from app.models import Tender
from app.repository import seed_from_fixtures, upsert_tender_row

app = FastAPI(title="EcoTender Tender Service", version="0.2.0")


class UpsertBody(BaseModel):
    country_code: str = "KZ"
    source_code: str
    external_id: str
    title: str
    description: str | None = None
    customer_name: str | None = None
    customer_external_id: str | None = None
    amount: float | None = None
    currency: str | None = "KZT"
    region_code: str | None = None
    region_name: str | None = None
    eco_category: str | None = None
    procurement_method: str | None = None
    participants_count: int | None = None
    area_sq_m: float | None = None
    duration_days: int | None = None
    winner_name: str | None = None
    amendments_count: int | None = None
    amendment_amount_ratio: float | None = None
    market_amount_est: float | None = None
    contractor_wins_2y: int | None = None
    contractor_win_rate: float | None = None
    risk_score: float | None = None
    risk_band: str | None = None
    lat: float | None = None
    lon: float | None = None
    published_at: str | None = None
    deadline_at: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


@app.on_event("startup")
async def startup() -> None:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(Tender))
        if not count:
            n = await seed_from_fixtures(session)
            print(f"seeded {n} tenders from fixtures")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "tender-service", "storage": "postgis"}


@app.post("/v1/tenders/upsert")
async def upsert_tender(body: UpsertBody, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    row = await upsert_tender_row(session, body.model_dump())
    return row.to_dict()


@app.get("/v1/tenders")
async def list_tenders(
    country: str | None = None,
    eco_category: str | None = None,
    source_code: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(Tender)
    if country:
        stmt = stmt.where(Tender.country_code == country)
    if eco_category:
        stmt = stmt.where(Tender.eco_category == eco_category)
    if source_code:
        stmt = stmt.where(Tender.source_code == source_code)
    if q:
        stmt = stmt.where(Tender.title.ilike(f"%{q}%"))

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = stmt.order_by(Tender.risk_score.desc().nullslast()).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [r.to_dict() for r in rows],
        "page": page,
        "size": size,
        "total": int(total or 0),
    }


@app.get("/v1/tenders/{tender_id}")
async def get_tender(tender_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from uuid import UUID

    stmt = select(Tender).where(Tender.external_id == tender_id)
    try:
        uid = UUID(tender_id)
        stmt = select(Tender).where(or_(Tender.id == uid, Tender.external_id == tender_id))
    except ValueError:
        pass
    row = (await session.execute(stmt)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Tender not found")
    return row.to_dict()


@app.get("/v1/contractors")
async def list_contractors(
    country: str | None = "KZ",
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(Tender).where(Tender.winner_name.is_not(None))
    if country:
        stmt = stmt.where(Tender.country_code == country)
    rows = (await session.execute(stmt)).scalars().all()
    by_name: dict[str, list[Tender]] = {}
    for r in rows:
        name = (r.winner_name or "").strip()
        if not name:
            continue
        by_name.setdefault(name, []).append(r)

    items = []
    for name, tenders in by_name.items():
        scores = [float(t.risk_score) for t in tenders if t.risk_score is not None]
        wins_2y = max((t.contractor_wins_2y or 0) for t in tenders)
        win_rate = max((t.contractor_win_rate or 0.0) for t in tenders)
        items.append(
            {
                "name": name,
                "tenders_count": len(tenders),
                "wins_2y": wins_2y,
                "win_rate": win_rate,
                "avg_risk_score": round(sum(scores) / len(scores), 1) if scores else None,
                "max_risk_score": max(scores) if scores else None,
                "high_risk_count": sum(1 for t in tenders if (t.risk_band or "") in ("high", "critical")),
            }
        )
    items.sort(key=lambda x: (x["high_risk_count"], x["avg_risk_score"] or 0), reverse=True)
    return {"items": items, "total": len(items)}


@app.get("/v1/contractors/{name}")
async def get_contractor(name: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from urllib.parse import unquote

    name = unquote(name)
    stmt = select(Tender).where(Tender.winner_name == name)
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        # case-insensitive contains
        stmt = select(Tender).where(Tender.winner_name.ilike(f"%{name}%"))
        rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="Contractor not found")

    scores = [float(t.risk_score) for t in rows if t.risk_score is not None]
    display_name = rows[0].winner_name or name
    return {
        "name": display_name,
        "tenders_count": len(rows),
        "wins_2y": max((t.contractor_wins_2y or 0) for t in rows),
        "win_rate": max((float(t.contractor_win_rate or 0) for t in rows), default=0.0),
        "avg_risk_score": round(sum(scores) / len(scores), 1) if scores else None,
        "max_risk_score": max(scores) if scores else None,
        "high_risk_count": sum(1 for t in rows if (t.risk_band or "") in ("high", "critical")),
        "tenders": [
            {
                "external_id": t.external_id,
                "title": t.title,
                "risk_score": t.risk_score,
                "risk_band": t.risk_band,
                "amount": t.amount,
                "eco_category": t.eco_category,
                "region_name": t.region_name,
            }
            for t in sorted(rows, key=lambda x: float(x.risk_score or 0), reverse=True)
        ],
    }
