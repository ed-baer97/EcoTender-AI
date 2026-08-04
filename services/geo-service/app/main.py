"""Geo service — Caspian KZ layers: tenders, coastline, ООПТ, work polygons, GIBS meta."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query

app = FastAPI(title="EcoTender Geo Service", version="0.2.0")


def load_tenders() -> list[dict[str, Any]]:
    path = Path("/data/fixtures/tenders.json")
    if not path.exists():
        path = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "tenders.json"
    return json.loads(path.read_text(encoding="utf-8"))


def square_around(lon: float, lat: float, area_sq_m: float | None) -> list[list[float]]:
    """Approx square polygon (lon,lat) from area."""
    side = math.sqrt(max(area_sq_m or 25_000, 5_000))
    # degrees ≈ meters / (111320 * cos(lat))
    dlat = (side / 2) / 111_320
    dlon = (side / 2) / (111_320 * max(0.2, math.cos(math.radians(lat))))
    return [
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]


# Simplified protected areas (ООПТ) near Kazakhstan Caspian coast — demo polygons
PROTECTED_AREAS = [
    {
        "name": "Государственный природный резерват «Акжайык» (буфер)",
        "code": "akzhayik",
        "coordinates": [
            [
                [51.6, 46.7],
                [52.1, 46.7],
                [52.1, 47.15],
                [51.6, 47.15],
                [51.6, 46.7],
            ]
        ],
    },
    {
        "name": "Устюртский государственный природный заповедник (северный буфер)",
        "code": "ustyurt",
        "coordinates": [
            [
                [53.8, 43.4],
                [54.4, 43.4],
                [54.4, 44.0],
                [53.8, 44.0],
                [53.8, 43.4],
            ]
        ],
    },
    {
        "name": "Прибрежная ООПТ — залив Кендерли (демо)",
        "code": "kenderli",
        "coordinates": [
            [
                [52.6, 42.7],
                [53.0, 42.7],
                [53.0, 43.05],
                [52.6, 43.05],
                [52.6, 42.7],
            ]
        ],
    },
]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "geo-service"}


@app.get("/v1/map/layers")
async def layers() -> dict[str, Any]:
    return {
        "layers": [
            {"code": "tenders", "name": "Эко-тендеры", "type": "point"},
            {"code": "coastline", "name": "Береговая линия", "type": "line"},
            {"code": "protected", "name": "ООПТ", "type": "polygon"},
            {"code": "work_polygons", "name": "Полигоны работ", "type": "polygon"},
            {
                "code": "gibs",
                "name": "NASA GIBS Blue Marble",
                "type": "raster",
                "tile_url": (
                    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
                    "BlueMarble_NextGeneration/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg"
                ),
                "attribution": "NASA GIBS",
                "opacity": 0.55,
            },
        ]
    }


@app.get("/v1/map/features")
async def features(
    bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat"),
    layers: str = Query("tenders"),
) -> dict[str, Any]:
    min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox.split(",")]
    layer_set = {x.strip() for x in layers.split(",")}
    feats: list[dict[str, Any]] = []

    if "tenders" in layer_set:
        for t in load_tenders():
            lon, lat = t.get("lon"), t.get("lat")
            if lon is None or lat is None:
                continue
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
            feats.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "kind": "tender",
                        "external_id": t["external_id"],
                        "title": t["title"],
                        "country_code": t["country_code"],
                        "eco_category": t.get("eco_category"),
                        "amount": t.get("amount"),
                        "risk_score": t.get("risk_score"),
                        "risk_band": t.get("risk_band"),
                        "winner_name": t.get("winner_name"),
                    },
                }
            )

    if "coastline" in layer_set:
        feats.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [50.0, 44.9],
                        [50.3, 44.5],
                        [50.5, 44.0],
                        [51.0, 43.5],
                        [51.2, 43.2],
                        [51.5, 43.0],
                        [51.8, 43.3],
                        [52.2, 43.6],
                        [52.8, 44.2],
                        [53.2, 45.0],
                        [53.5, 45.8],
                        [53.3, 46.5],
                        [52.8, 47.0],
                        [52.0, 47.2],
                        [51.5, 47.1],
                    ],
                },
                "properties": {"kind": "coastline", "source": "demo-kz-caspian", "country_code": "KZ"},
            }
        )

    if "protected" in layer_set:
        for pa in PROTECTED_AREAS:
            ring = pa["coordinates"][0]
            # bbox filter: any vertex inside
            if not any(min_lon <= p[0] <= max_lon and min_lat <= p[1] <= max_lat for p in ring):
                continue
            feats.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": pa["coordinates"]},
                    "properties": {
                        "kind": "protected",
                        "name": pa["name"],
                        "code": pa["code"],
                        "layer_code": "protected",
                    },
                }
            )

    if "work_polygons" in layer_set:
        for t in load_tenders():
            lon, lat = t.get("lon"), t.get("lat")
            if lon is None or lat is None:
                continue
            if t.get("risk_band") not in ("high", "critical"):
                continue
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
            ring = square_around(float(lon), float(lat), t.get("area_sq_m"))
            feats.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {
                        "kind": "work_polygon",
                        "external_id": t["external_id"],
                        "title": t["title"],
                        "risk_band": t.get("risk_band"),
                        "area_sq_m": t.get("area_sq_m"),
                    },
                }
            )

    return {"type": "FeatureCollection", "features": feats}
