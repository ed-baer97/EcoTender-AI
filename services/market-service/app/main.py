import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="EcoTender Market Service", version="0.1.0")


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


@app.post("/v1/market/estimate")
async def estimate(req: EstimateRequest) -> dict[str, Any]:
    catalog = {p["sku"]: p for p in load_prices()}
    lines = []
    total = 0.0
    for wi in req.work_items:
        price = catalog.get(wi.sku or "", {}).get("price")
        if price is None:
            norm_name = _norm(wi.name)
            for sku, hints in SKU_HINTS.items():
                if any(h in norm_name for h in hints):
                    price = catalog.get(sku, {}).get("price")
                    break
        if price is None:
            # naive name contains match
            norm_name = _norm(wi.name)
            for p in catalog.values():
                if _norm(p["name"]) in norm_name or norm_name[:12] in _norm(p["name"]):
                    price = p["price"]
                    break
        price = float(price or 0)
        line_total = price * wi.quantity
        total += line_total
        lines.append({"name": wi.name, "unit_price": price, "line_total": line_total})
    return {"currency": "KZT", "estimated_total": total, "lines": lines, "region_code": req.region_code}
