import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="EcoTender Market Service", version="0.2.0")

MATCH_CONFIDENCE = {
    "sku": 0.95,
    "hint": 0.65,
    "fuzzy": 0.35,
    "none": 0.0,
}


def load_prices() -> list[dict[str, Any]]:
    path = Path("/data/fixtures/market_prices.json")
    if not path.exists():
        path = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "market_prices.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("-", " ").replace("_", " ").split())


SKU_HINTS = {
    "BOOM_BARRIER_M": ("бон", "бонов", "загражден"),
    "OIL_SOIL_REMOVE_M3": ("нефтезагряз", "грунт", "утилизац", "очистк"),
    "WATER_LAB_SAMPLE": ("воды", "вода", "лаборатор", "монитор"),
    "GEOTEXTILE_M2": ("геотекст", "берегоукреп", "укреп"),
    "DREDGE_M3": ("дноуглуб", "канал", "фарватер"),
}


class WorkItem(BaseModel):
    name: str
    unit: str
    quantity: float
    sku: str | None = None


class EstimateRequest(BaseModel):
    work_items: list[WorkItem] = Field(default_factory=list)
    region_code: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "market-service"}


@app.get("/v1/market/items")
async def items() -> dict[str, Any]:
    return {"items": load_prices()}


def _match_price(wi: WorkItem, catalog: dict[str, dict[str, Any]]) -> tuple[float, str, str | None]:
    """Return (unit_price, match_method, sku)."""
    if wi.sku and wi.sku in catalog:
        return float(catalog[wi.sku].get("price") or 0), "sku", wi.sku

    norm_name = _norm(wi.name)
    for sku, hints in SKU_HINTS.items():
        if any(h in norm_name for h in hints):
            price = catalog.get(sku, {}).get("price")
            if price is not None:
                return float(price), "hint", sku

    for p in catalog.values():
        pname = _norm(p["name"])
        if pname in norm_name or (norm_name[:12] and norm_name[:12] in pname):
            return float(p.get("price") or 0), "fuzzy", str(p.get("sku") or "")

    return 0.0, "none", None


@app.post("/v1/market/estimate")
async def estimate(req: EstimateRequest) -> dict[str, Any]:
    catalog = {p["sku"]: p for p in load_prices()}
    lines = []
    total = 0.0
    confidences: list[float] = []
    for wi in req.work_items:
        price, method, sku = _match_price(wi, catalog)
        line_total = price * wi.quantity
        total += line_total
        conf = MATCH_CONFIDENCE.get(method, 0.0)
        if method != "none":
            confidences.append(conf)
        lines.append(
            {
                "name": wi.name,
                "unit_price": price,
                "line_total": line_total,
                "match_method": method,
                "sku": sku,
                "confidence": conf,
            }
        )

    # Overall: best matched line; empty / all-none → 0
    confidence = max(confidences) if confidences else 0.0
    # Penalize when only fuzzy matches
    if confidences and max(confidences) <= MATCH_CONFIDENCE["fuzzy"]:
        confidence = min(confidence, MATCH_CONFIDENCE["fuzzy"])

    return {
        "currency": "KZT",
        "estimated_total": total,
        "confidence": round(confidence, 3),
        "usable": confidence >= 0.55 and total > 0,
        "lines": lines,
        "region_code": req.region_code,
    }
