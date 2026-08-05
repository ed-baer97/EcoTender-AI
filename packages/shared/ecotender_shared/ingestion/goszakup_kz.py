"""Kazakhstan goszakup.gov.kz OWS v3 adapter.

Docs: https://goszakup.gov.kz/ru/developer/ows_v3
Base: https://ows.goszakup.gov.kz
Auth: Authorization: Bearer <token>  (issue via Центр Электронных Финансов / portal profile)

Without GOSZAKUP_TOKEN uses offline sample under data/fixtures/goszakup_sample.json.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ecotender_shared.ingestion.base import RawTenderPage, SourceAdapter
from ecotender_shared.ingestion.eco_filter import (
    classify_eco_category,
    is_caspian_kz_related,
    is_eco_related,
    map_kz_region,
)
from ecotender_shared.schemas import NormalizedTender

BASE_URL_DEFAULT = "https://ows.goszakup.gov.kz"
TRADE_METHOD_LABELS = {
    2: "open_tender",
    3: "request_price",
    6: "from_one_source",
    7: "auction",
    132: "open_tender",
}


class KazakhstanGoszakupAdapter(SourceAdapter):
    source_code = "KZ_GOSZAKUP_OWS_V3"
    country_code = "KZ"

    def __init__(
        self,
        token: str | None = None,
        *,
        limit: int = 50,
        max_pages: int = 3,
        sample_path: str | Path | None = None,
        prefer_caspian: bool = True,
    ) -> None:
        from ecotender_shared.runtime_secrets import get_config_value

        self.token = (
            token
            or get_config_value("GOSZAKUP_TOKEN")
            or os.getenv("GOSZAKUP_TOKEN")
            or os.getenv("GOSZAKUP_API_TOKEN")
        )
        self.limit = limit
        self.max_pages = max_pages
        self.prefer_caspian = prefer_caspian
        if sample_path:
            self.sample_path = Path(sample_path)
        else:
            candidates = [
                Path("/data/fixtures/goszakup_sample.json"),
                Path(__file__).resolve().parents[4] / "data" / "fixtures" / "goszakup_sample.json",
            ]
            self.sample_path = next((p for p in candidates if p.exists()), candidates[-1])

    @property
    def base_url(self) -> str:
        from ecotender_shared.runtime_secrets import get_config_value

        return (
            get_config_value("GOSZAKUP_BASE_URL", BASE_URL_DEFAULT) or BASE_URL_DEFAULT
        ).rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _load_sample(self) -> dict[str, Any]:
        if not self.sample_path.exists():
            raise FileNotFoundError(
                f"GOSZAKUP_TOKEN not set and sample missing: {self.sample_path}. "
                "Obtain token at goszakup.gov.kz (Профиль → Выпуск токена)."
            )
        return json.loads(self.sample_path.read_text(encoding="utf-8"))

    def _passes_filter(self, item: dict[str, Any]) -> bool:
        blob = " ".join(
            str(item.get(k) or "")
            for k in ("name_ru", "name_kz", "org_name_ru", "customer_name_ru", "number_anno")
        )
        if not is_eco_related(blob):
            return False
        if self.prefer_caspian and not is_caspian_kz_related(blob):
            # keep strong eco matches even without region hint
            strong = ("каспий", "нефтезагрязн", "рекультив", "дноуглуб", "бонов")
            if not any(s in blob.lower() for s in strong):
                return False
        return True

    def discover_sync(self, cursor: str | None = None) -> Iterator[str]:
        """Yield announcement ids (as strings)."""
        if not self.token:
            sample = self._load_sample()
            for item in sample.get("items", []):
                if self._passes_filter(item) or sample.get("prefiltered"):
                    yield str(item["id"])
            return

        path = cursor or f"/v3/trd-buy/all?limit={self.limit}"
        pages = 0
        with httpx.Client(base_url=self.base_url, headers=self._headers(), timeout=45.0) as client:
            while path and pages < self.max_pages:
                resp = client.get(path if path.startswith("/") else f"/{path}")
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("items") or []:
                    if self._passes_filter(item):
                        yield str(item["id"])
                next_page = data.get("next_page")
                path = next_page
                pages += 1

    async def discover(self, cursor: str | None = None) -> AsyncIterator[str]:
        for ref in self.discover_sync(cursor):
            yield ref

    def fetch_sync(self, ref: str) -> RawTenderPage:
        if not self.token:
            sample = self._load_sample()
            item = next((x for x in sample.get("items", []) if str(x.get("id")) == str(ref)), None)
            if item is None:
                raise KeyError(f"announcement {ref} not in sample")
            payload = json.dumps(item, ensure_ascii=False).encode("utf-8")
            return RawTenderPage(
                source_code=self.source_code,
                country_code=self.country_code,
                external_id=str(ref),
                content_type="application/json",
                payload=payload,
            )

        with httpx.Client(base_url=self.base_url, headers=self._headers(), timeout=45.0) as client:
            resp = client.get(f"/v3/trd-buy/{ref}")
            resp.raise_for_status()
            data = resp.json()
            # API may return object or {items:[...]} depending on endpoint
            if isinstance(data, dict) and "items" in data and data["items"]:
                item = data["items"][0]
            elif isinstance(data, dict) and "id" in data:
                item = data
            else:
                item = data
            payload = json.dumps(item, ensure_ascii=False).encode("utf-8")
            return RawTenderPage(
                source_code=self.source_code,
                country_code=self.country_code,
                external_id=str(ref),
                content_type="application/json",
                payload=payload,
            )

    async def fetch(self, ref: str) -> RawTenderPage:
        return self.fetch_sync(ref)

    def normalize(self, raw: RawTenderPage) -> NormalizedTender:
        data = json.loads(raw.payload.decode("utf-8"))
        title = data.get("name_ru") or data.get("name_kz") or f"Объявление {data.get('number_anno')}"
        region_blob = " ".join(
            str(data.get(k) or "")
            for k in ("name_ru", "org_name_ru", "customer_name_ru")
        )
        region_code, region_name, lat, lon = map_kz_region(region_blob)
        method_id = data.get("ref_trade_methods_id")
        method = TRADE_METHOD_LABELS.get(int(method_id or 0), "open_tender")
        if method == "from_one_source":
            method = "single_source"

        published = _parse_dt(data.get("publish_date"))
        deadline = _parse_dt(data.get("end_date"))
        amount = data.get("total_sum")
        try:
            amount_f = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            amount_f = None

        return NormalizedTender(
            country_code=self.country_code,
            source_code=self.source_code,
            external_id=str(data.get("number_anno") or data.get("id")),
            title=str(title),
            description=str(data.get("name_kz") or ""),
            customer_name=data.get("customer_name_ru") or data.get("org_name_ru"),
            customer_external_id=data.get("customer_bin") or data.get("org_bin"),
            published_at=published,
            deadline_at=deadline,
            amount=amount_f,
            currency="KZT",
            region_code=region_code,
            region_name=region_name,
            eco_category=classify_eco_category(title),
            procurement_method=method,
            participants_count=None,
            lat=lat,
            lon=lon,
            winner_external_id=data.get("biin_supplier"),
            extras={
                "goszakup_id": data.get("id"),
                "number_anno": data.get("number_anno"),
                "count_lots": data.get("count_lots"),
                "ref_buy_status_id": data.get("ref_buy_status_id"),
                "org_bin": data.get("org_bin"),
                "system_id": data.get("system_id"),
                "raw_keys": sorted(data.keys()),
            },
        )


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None
