"""FastAPI tender-service backed by PostgreSQL + PostGIS."""

from __future__ import annotations

import os
import uuid
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, get_session
from app.minio_store import ALLOWED_PHOTO_TYPES, MAX_PHOTO_BYTES, fetch_bytes, store_bytes
from app.models import PatrolReport, Tender
from app.repository import delete_by_source, delete_synthetic, seed_from_fixtures, upsert_tender_row

app = FastAPI(title="EcoTender Tender Service", version="0.3.0")


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


async def _resolve_tender(tender_ref: str, session: AsyncSession) -> Tender:
    stmt = select(Tender).where(Tender.external_id == tender_ref)
    try:
        uid = UUID(tender_ref)
        stmt = select(Tender).where(or_(Tender.id == uid, Tender.external_id == tender_ref))
    except ValueError:
        pass
    row = (await session.execute(stmt)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Tender not found")
    return row


def _patrol_photo_url(tender_ref: str, report_id: uuid.UUID) -> str:
    # Path relative to gateway /api/v1
    return f"/tenders/{tender_ref}/patrol/{report_id}/photo"


def _report_dict(report: PatrolReport, tender_ref: str) -> dict[str, Any]:
    photo_url = None
    if report.photo_key:
        photo_url = _patrol_photo_url(tender_ref, report.id)
    return report.to_dict(photo_url=photo_url)


@app.on_event("startup")
async def startup() -> None:
    if os.getenv("SEED_FIXTURES", "").lower() not in ("1", "true", "yes"):
        return
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


@app.delete("/v1/tenders/by-source/{source_code}")
async def purge_by_source(source_code: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if source_code == "synthetic":
        deleted = await delete_synthetic(session)
    else:
        deleted = await delete_by_source(session, source_code)
    return {"deleted": deleted, "source_code": source_code}


@app.get("/v1/tenders/{tender_id}")
async def get_tender(tender_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    row = await _resolve_tender(tender_id, session)
    return row.to_dict()


@app.get("/v1/tenders/{tender_ref}/patrol")
async def list_patrol_reports(
    tender_ref: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    tender = await _resolve_tender(tender_ref, session)
    stmt = (
        select(PatrolReport)
        .where(PatrolReport.tender_id == tender.id)
        .order_by(PatrolReport.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    ref = str(tender.id)
    return {
        "items": [_report_dict(r, ref) for r in rows],
        "total": len(rows),
    }


@app.post("/v1/tenders/{tender_ref}/patrol")
async def create_patrol_report(
    tender_ref: str,
    author_name: str = Form(...),
    body: str = Form(...),
    photo: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    tender = await _resolve_tender(tender_ref, session)
    name = (author_name or "").strip()
    text = (body or "").strip()
    if not name or len(name) > 80:
        raise HTTPException(status_code=400, detail="author_name must be 1–80 characters")
    if not text or len(text) > 2000:
        raise HTTPException(status_code=400, detail="body must be 1–2000 characters")

    photo_bucket = None
    photo_key = None
    photo_content_type = None
    if photo is not None and photo.filename:
        content_type = (photo.content_type or "").split(";")[0].strip().lower()
        if content_type not in ALLOWED_PHOTO_TYPES:
            raise HTTPException(status_code=400, detail="photo must be jpeg, png, or webp")
        data = await photo.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty photo")
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=400, detail="photo must be ≤ 5 MB")
        try:
            stored = store_bytes(
                data,
                object_prefix=f"patrol/{tender.id}",
                filename=photo.filename or f"photo{ALLOWED_PHOTO_TYPES[content_type]}",
                content_type=content_type,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"photo storage unavailable: {exc}") from exc
        photo_bucket = stored.bucket
        photo_key = stored.object_key
        photo_content_type = stored.content_type

    report = PatrolReport(
        id=uuid.uuid4(),
        tender_id=tender.id,
        author_name=name,
        body=text,
        photo_bucket=photo_bucket,
        photo_key=photo_key,
        photo_content_type=photo_content_type,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return _report_dict(report, str(tender.id))


@app.get("/v1/tenders/{tender_ref}/patrol/{report_id}/photo")
async def get_patrol_photo(
    tender_ref: str,
    report_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    tender = await _resolve_tender(tender_ref, session)
    try:
        rid = UUID(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    report = (
        await session.execute(
            select(PatrolReport).where(
                PatrolReport.id == rid,
                PatrolReport.tender_id == tender.id,
            )
        )
    ).scalar_one_or_none()
    if not report or not report.photo_key or not report.photo_bucket:
        raise HTTPException(status_code=404, detail="Photo not found")
    try:
        data, header_ct = fetch_bytes(report.photo_bucket, report.photo_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"photo storage unavailable: {exc}") from exc
    media = report.photo_content_type or header_ct or "application/octet-stream"
    return Response(content=data, media_type=media)


@app.get("/v1/tenders/{tender_id}/artifacts")
async def get_tender_artifacts(tender_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    row = await get_tender(tender_id, session)
    gos = ((row.get("extras") or {}).get("goszakup") or {})
    return {
        "external_id": row.get("external_id"),
        "detail_url": (row.get("extras") or {}).get("detail_url"),
        "search_filters": (row.get("extras") or {}).get("search_filters") or {},
        "matched_keywords": (row.get("extras") or {}).get("matched_keywords") or [],
        "tabs": gos.get("tabs") or [],
        "documents": gos.get("documents") or [],
        "lots": gos.get("lots") or [],
        "bidders": gos.get("bidders") or [],
        "protocols": gos.get("protocols") or [],
        "contracts": gos.get("contracts") or [],
        "stored_assets": gos.get("stored_assets") or [],
        "raw_tab_stats": gos.get("raw_tab_stats") or {},
    }


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
