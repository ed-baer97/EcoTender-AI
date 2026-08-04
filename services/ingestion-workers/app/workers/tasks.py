"""Celery ingest tasks — SourceAdapter pipeline."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.workers.celery_app import celery_app


def _adapter(source_code: str):
    if source_code in ("KZ_GOSZAKUP_OWS_V3", "KZ_GOSZAKUP", "goszakup"):
        from ecotender_shared.ingestion.goszakup_kz import KazakhstanGoszakupAdapter

        return KazakhstanGoszakupAdapter(
            limit=int(os.getenv("GOSZAKUP_PAGE_LIMIT", "50")),
            max_pages=int(os.getenv("GOSZAKUP_MAX_PAGES", "3")),
        )
    if source_code in ("FIXTURES_CASPIAN", "fixtures"):
        from pathlib import Path

        from ecotender_shared.ingestion.fixture_adapter import FixtureAdapter

        path = Path("/data/fixtures/tenders.json")
        if not path.exists():
            path = Path(__file__).resolve().parents[4] / "data" / "fixtures" / "tenders.json"
        return FixtureAdapter(path)
    raise ValueError(f"Unknown source_code={source_code}")


def _upsert_tender(normalized: dict[str, Any]) -> dict[str, Any]:
    base = os.getenv("TENDER_SERVICE_URL", "http://tender-service:8001").rstrip("/")
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{base}/v1/tenders/upsert", json=normalized)
        resp.raise_for_status()
        return resp.json()


@celery_app.task(name="app.workers.tasks.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="app.workers.tasks.crawl_source", bind=True)
def crawl_source(self, source_code: str = "KZ_GOSZAKUP_OWS_V3") -> dict[str, Any]:
    """Discover → fetch → normalize → upsert into tender-service."""
    adapter = _adapter(source_code)
    mode = "live" if getattr(adapter, "token", None) else "sample_offline"
    pages_ok = 0
    pages_fail = 0
    upserted: list[str] = []
    errors: list[str] = []

    try:
        refs = list(adapter.discover_sync()) if hasattr(adapter, "discover_sync") else []
        if not refs and hasattr(adapter, "discover"):
            # FixtureAdapter is async-only discover
            import asyncio

            async def _collect() -> list[str]:
                out: list[str] = []
                async for r in adapter.discover():
                    out.append(r)
                return out

            refs = asyncio.run(_collect())
    except Exception as exc:  # noqa: BLE001
        return {
            "source_code": source_code,
            "status": "failed",
            "mode": mode,
            "error": str(exc),
            "pages_ok": 0,
            "pages_fail": 0,
        }

    for ref in refs:
        try:
            raw = adapter.fetch_sync(ref) if hasattr(adapter, "fetch_sync") else None
            if raw is None:
                import asyncio

                raw = asyncio.run(adapter.fetch(ref))
            normalized = adapter.normalize(raw)
            payload = normalized.model_dump(mode="json")
            result = _upsert_tender(payload)
            upserted.append(result.get("external_id") or normalized.external_id)
            pages_ok += 1
        except Exception as exc:  # noqa: BLE001
            pages_fail += 1
            errors.append(f"{ref}: {exc}")

    return {
        "source_code": source_code,
        "status": "ok" if pages_ok else "empty_or_failed",
        "mode": mode,
        "docs": "https://goszakup.gov.kz/ru/developer/ows_v3",
        "discovered": len(refs),
        "pages_ok": pages_ok,
        "pages_fail": pages_fail,
        "upserted": upserted[:50],
        "errors": errors[:10],
        "task_id": getattr(self.request, "id", None),
    }
