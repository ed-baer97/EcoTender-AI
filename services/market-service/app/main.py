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
            # naive name contains match
            for p in catalog.values():
                if wi.name.lower()[:12] in p["name"].lower():
                    price = p["price"]
                    break
        price = float(price or 0)
        line_total = price * wi.quantity
        total += line_total
        lines.append({"name": wi.name, "unit_price": price, "line_total": line_total})
    return {"currency": "KZT", "estimated_total": total, "lines": lines, "region_code": req.region_code}
