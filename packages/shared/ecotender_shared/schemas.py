from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class NormalizedTender(BaseModel):
    """Canonical tender DTO produced by any SourceAdapter."""

    country_code: str = Field(..., min_length=2, max_length=2)
    source_code: str
    external_id: str
    title: str
    description: str | None = None
    customer_name: str | None = None
    customer_external_id: str | None = None
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    amount: float | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    region_code: str | None = None
    region_name: str | None = None
    eco_category: str | None = None
    procurement_method: str | None = None
    participants_count: int | None = None
    area_sq_m: float | None = None
    duration_days: int | None = None
    lat: float | None = None
    lon: float | None = None
    winner_name: str | None = None
    winner_external_id: str | None = None
    amendments_count: int = 0
    amendment_amount_ratio: float = 0.0
    extras: dict[str, Any] = Field(default_factory=dict)


class DomainEvent(BaseModel):
    event_id: UUID
    event_type: str
    occurred_at: datetime
    producer: str
    schema_version: int = 1
    payload: dict[str, Any]


class RiskReasonDTO(BaseModel):
    code: str
    severity: str
    message_ru: str
    contribution: float | None = None


class RiskAssessmentDTO(BaseModel):
    tender_id: UUID
    risk_score: float
    risk_band: str
    corruption_proba: float
    model_version: str
    scored_at: datetime
    explanation: str | None = None
    reasons: list[RiskReasonDTO] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    feature_vector: dict[str, Any] = Field(default_factory=dict)
