from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

from ecotender_shared.ingestion.base import RawTenderPage, SourceAdapter
from ecotender_shared.schemas import NormalizedTender


class FixtureAdapter(SourceAdapter):
    """Deterministic demo source — always works offline for the jury."""

    source_code = "FIXTURES_CASPIAN"
    country_code = "KZ"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._rows: list[dict] = json.loads(self.path.read_text(encoding="utf-8"))

    async def discover(self, cursor: str | None = None) -> AsyncIterator[str]:
        for row in self._rows:
            yield str(row["external_id"])

    async def fetch(self, ref: str) -> RawTenderPage:
        row = next(r for r in self._rows if str(r["external_id"]) == ref)
        payload = json.dumps(row, ensure_ascii=False).encode("utf-8")
        return RawTenderPage(
            source_code=self.source_code,
            country_code=row.get("country_code", self.country_code),
            external_id=ref,
            content_type="application/json",
            payload=payload,
        )

    def normalize(self, raw: RawTenderPage) -> NormalizedTender:
        data = json.loads(raw.payload.decode("utf-8"))
        return NormalizedTender(
            country_code=data["country_code"],
            source_code=self.source_code,
            external_id=str(data["external_id"]),
            title=data["title"],
            description=data.get("description"),
            customer_name=data.get("customer_name"),
            amount=data.get("amount"),
            currency=data.get("currency", "KZT"),
            region_code=data.get("region_code"),
            region_name=data.get("region_name"),
            eco_category=data.get("eco_category"),
            procurement_method=data.get("procurement_method"),
            participants_count=data.get("participants_count"),
            area_sq_m=data.get("area_sq_m"),
            duration_days=data.get("duration_days"),
            lat=data.get("lat"),
            lon=data.get("lon"),
            winner_name=data.get("winner_name"),
            amendments_count=data.get("amendments_count", 0),
            amendment_amount_ratio=data.get("amendment_amount_ratio", 0.0),
            extras=data.get("extras", {}),
        )
