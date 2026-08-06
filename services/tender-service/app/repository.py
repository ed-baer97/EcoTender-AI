"""Seed / upsert helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tender


def heuristic_risk(row: dict[str, Any]) -> tuple[float, str]:
    """Keep in sync with risk-engine heuristic_proba for list/map chips."""
    extras = row.get("extras") or {}
    gos = extras.get("goszakup") or {}
    amount = float(row.get("amount") or 0)
    market_raw = row.get("market_amount_est")
    market = float(market_raw) if market_raw not in (None, "", 0, 0.0) else None
    parts_raw = row.get("participants_count")
    parts = int(parts_raw) if parts_raw not in (None, "") else -1
    wr = float(row.get("contractor_win_rate") or 0)
    wins = int(row.get("contractor_wins_2y") or 0)
    amend = float(row.get("amendment_amount_ratio") or 0)
    method = str(row.get("procurement_method") or "")
    eco = str(row.get("eco_category") or "other")

    score = 0.08
    if market and market > 0:
        over = amount / market
        score += 0.22 * (1.0 if over > 1.4 else max(0.0, (over - 1.0) / 0.4))
        score += 0.12 * min(1.0, max(0.0, over - 1.0))
    if parts == 1:
        score += 0.22
    elif 0 < parts <= 2:
        score += 0.12
    elif parts < 0:
        score += 0.06
    if method == "single_source":
        score += 0.28
    elif method == "request_price":
        score += 0.10
    if wr > 0.7 and wins >= 5:
        score += 0.18
    else:
        score += 0.08 * wr
    score += 0.14 * min(1.0, amend / 0.25 if amend else 0.0)
    if amount >= 1_000_000_000:
        score += 0.18
    elif amount >= 100_000_000:
        score += 0.12
    elif amount >= 10_000_000:
        score += 0.08
    elif amount >= 1_000_000:
        score += 0.04
    elif amount > 0 and amount < 100_000:
        score -= 0.02
    if eco in {
        "oil_spill_response",
        "dredging",
        "reclamation",
        "shore_protection",
        "coastal_cleanup",
    }:
        score += 0.10
    if eco == "oil_spill_response":
        score += 0.06
    if row.get("region_code") in ("KZ-MAN", "KZ-ATY") and eco in {
        "oil_spill_response",
        "dredging",
        "reclamation",
        "shore_protection",
        "coastal_cleanup",
    }:
        score += 0.05
    if len(gos.get("lots") or []) >= 3:
        score += 0.05
    if len(gos.get("documents") or []) == 0:
        score += 0.05
    if len(gos.get("protocols") or []) == 0:
        score += 0.04
    if len(gos.get("contracts") or []) > 0:
        score += 0.05

    s = round(min(1.0, max(0.0, score)) * 100, 1)
    band = "critical" if s >= 80 else "high" if s >= 60 else "medium" if s >= 30 else "low"
    return s, band


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def point_wkt(lat: float | None, lon: float | None) -> WKTElement | None:
    if lat is None or lon is None:
        return None
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


async def upsert_tender_row(session: AsyncSession, payload: dict[str, Any]) -> Tender:
    source_code = payload.get("source_code") or "FIXTURES_CASPIAN"
    external_id = str(payload["external_id"])
    risk_score = payload.get("risk_score")
    risk_band = payload.get("risk_band")
    if risk_score is None or risk_band is None:
        risk_score, risk_band = heuristic_risk(payload)

    result = await session.execute(
        select(Tender).where(Tender.source_code == source_code, Tender.external_id == external_id)
    )
    row = result.scalar_one_or_none()
    lat = payload.get("lat")
    lon = payload.get("lon")
    geom = point_wkt(lat, lon)

    fields = {
        "country_code": payload.get("country_code") or "KZ",
        "source_code": source_code,
        "external_id": external_id,
        "title": payload["title"],
        "description": payload.get("description"),
        "customer_name": payload.get("customer_name"),
        "customer_external_id": payload.get("customer_external_id"),
        "amount": payload.get("amount"),
        "currency": payload.get("currency") or "KZT",
        "region_code": payload.get("region_code"),
        "region_name": payload.get("region_name"),
        "eco_category": payload.get("eco_category"),
        "procurement_method": payload.get("procurement_method"),
        "participants_count": payload.get("participants_count"),
        "area_sq_m": payload.get("area_sq_m"),
        "duration_days": payload.get("duration_days"),
        "winner_name": payload.get("winner_name"),
        "amendments_count": payload.get("amendments_count"),
        "amendment_amount_ratio": payload.get("amendment_amount_ratio"),
        "market_amount_est": payload.get("market_amount_est"),
        "contractor_wins_2y": payload.get("contractor_wins_2y"),
        "contractor_win_rate": payload.get("contractor_win_rate"),
        "risk_score": float(risk_score) if risk_score is not None else None,
        "risk_band": risk_band,
        "lat": lat,
        "lon": lon,
        "geom": geom,
        "published_at": _parse_dt(payload.get("published_at")),
        "deadline_at": _parse_dt(payload.get("deadline_at")),
        "extras": payload.get("extras") or {},
    }

    if row is None:
        row = Tender(id=uuid4(), **fields)
        session.add(row)
    else:
        for k, v in fields.items():
            setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_by_source(session: AsyncSession, source_code: str) -> int:
    result = await session.execute(delete(Tender).where(Tender.source_code == source_code))
    await session.commit()
    return int(result.rowcount or 0)


async def delete_synthetic(session: AsyncSession) -> int:
    """Remove demo fixtures (FIXTURES_CASPIAN + KZ-ECO-* ids)."""
    result = await session.execute(
        delete(Tender).where(
            (Tender.source_code == "FIXTURES_CASPIAN") | Tender.external_id.like("KZ-ECO-%")
        )
    )
    await session.commit()
    return int(result.rowcount or 0)


async def seed_from_fixtures(session: AsyncSession) -> int:
    path = Path("/data/fixtures/tenders.json")
    if not path.exists():
        path = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "tenders.json"
    if not path.exists():
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for raw in rows:
        raw = {**raw, "source_code": raw.get("source_code") or "FIXTURES_CASPIAN"}
        await upsert_tender_row(session, raw)
        count += 1
    return count
