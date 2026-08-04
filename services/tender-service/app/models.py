"""Tender ORM model — schema tender, PostGIS point."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Tender(Base):
    __tablename__ = "tenders"
    __table_args__ = (
        UniqueConstraint("source_code", "external_id", name="uq_tender_source_ext"),
        {"schema": "tender"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    country_code: Mapped[str] = mapped_column(String(2), index=True, default="KZ")
    source_code: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True, default="KZT")
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    region_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    eco_category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    procurement_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    participants_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area_sq_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    amendments_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amendment_amount_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_amount_est: Mapped[float | None] = mapped_column(Float, nullable=True)
    contractor_wins_2y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contractor_win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    risk_band: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    geom: Mapped[Any | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extras: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "country_code": self.country_code,
            "source_code": self.source_code,
            "external_id": self.external_id,
            "title": self.title,
            "description": self.description,
            "customer_name": self.customer_name,
            "customer_external_id": self.customer_external_id,
            "amount": self.amount,
            "currency": self.currency,
            "region_code": self.region_code,
            "region_name": self.region_name,
            "eco_category": self.eco_category,
            "procurement_method": self.procurement_method,
            "participants_count": self.participants_count,
            "area_sq_m": self.area_sq_m,
            "duration_days": self.duration_days,
            "winner_name": self.winner_name,
            "amendments_count": self.amendments_count,
            "amendment_amount_ratio": self.amendment_amount_ratio,
            "market_amount_est": self.market_amount_est,
            "contractor_wins_2y": self.contractor_wins_2y,
            "contractor_win_rate": self.contractor_win_rate,
            "risk_score": self.risk_score,
            "risk_band": self.risk_band,
            "lat": self.lat,
            "lon": self.lon,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "extras": self.extras or {},
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
        }
