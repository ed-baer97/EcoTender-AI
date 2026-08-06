"""Celery ingest tasks — SourceAdapter pipeline."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.workers.celery_app import celery_app
from app.workers.raw_store import store_bytes


def _adapter(source_code: str):
    if source_code in (
        "KZ_GOSZAKUP_OWS_V3",
        "KZ_GOSZAKUP",
        "goszakup",
        "KZ_GOSZAKUP_PLAYWRIGHT",
        "goszakup_playwright",
        "playwright",
    ):
        from ecotender_shared.ingestion.goszakup_factory import resolve_goszakup_adapter

        return resolve_goszakup_adapter(source_code)
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


def _estimate_market(normalized: dict[str, Any]) -> float | None:
    base = os.getenv("MARKET_SERVICE_URL", "http://market-service:8002").rstrip("/")
    extras = normalized.get("extras") or {}
    gos = extras.get("goszakup") or {}
    work_items = []
    for lot in gos.get("lots") or []:
        name = str(lot.get("name") or "").strip()
        if not name:
            continue
        work_items.append({"name": name, "unit": "item", "quantity": 1})
    if not work_items:
        title = str(normalized.get("title") or "").strip()
        if title:
            work_items.append({"name": title, "unit": "item", "quantity": 1})
    if not work_items:
        return None
    payload = {"work_items": work_items[:20], "region_code": normalized.get("region_code")}
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(f"{base}/v1/market/estimate", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return float(data.get("estimated_total") or 0) or None
    except Exception:
        return None


def _persist_raw_assets(normalized: dict[str, Any]) -> dict[str, Any]:
    from ecotender_shared.doc_extract import (
        DOC_KINDS,
        build_extract_record,
        extract_text_from_bytes,
        merge_doc_extracts,
    )

    extract_on_ingest = os.getenv("GOSZAKUP_PW_EXTRACT_ON_INGEST", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    extras = normalized.get("extras") or {}
    gos = extras.get("goszakup") or {}
    raw_assets = gos.pop("raw_assets", []) or []
    if not raw_assets:
        return normalized
    stored_assets: list[dict[str, Any]] = []
    new_extracts: list[dict[str, Any]] = []
    for asset in raw_assets:
        try:
            body = asset.get("body_b64")
            if not body:
                continue
            import base64

            blob = base64.b64decode(body)
            kind = str(asset.get("kind") or "raw")
            stored = store_bytes(
                blob,
                object_prefix=f"goszakup/{normalized.get('external_id')}/{kind}",
                filename=str(asset.get("name") or "artifact.bin"),
                content_type=str(asset.get("content_type") or "application/octet-stream"),
            )
            meta = stored.to_meta(
                kind=kind,
                source_url=asset.get("source_url"),
                tab_name=asset.get("tab_name"),
            )
            stored_assets.append(meta)
            if extract_on_ingest and kind in DOC_KINDS:
                excerpt, err = extract_text_from_bytes(
                    blob,
                    content_type=str(asset.get("content_type") or meta.get("content_type") or ""),
                    filename=str(asset.get("name") or ""),
                )
                new_extracts.append(
                    build_extract_record(
                        name=str(asset.get("name") or meta.get("object_key") or "document"),
                        kind=kind,
                        sha256=meta.get("sha256"),
                        excerpt=excerpt,
                        error=err,
                        content_type=meta.get("content_type"),
                        object_key=meta.get("object_key"),
                        group_name=asset.get("group_name") or asset.get("tab_name"),
                    )
                )
        except Exception as exc:
            stored_assets.append(
                {
                    "kind": asset.get("kind"),
                    "source_url": asset.get("source_url"),
                    "tab_name": asset.get("tab_name"),
                    "error": str(exc),
                }
            )
    for doc in gos.get("documents") or []:
        url = doc.get("url")
        meta = next(
            (
                x
                for x in stored_assets
                if x.get("source_url") == url and x.get("kind") in DOC_KINDS
            ),
            None,
        )
        if meta:
            doc["object_key"] = meta.get("object_key")
            doc["bucket"] = meta.get("bucket")
            doc["sha256"] = meta.get("sha256")
            doc["content_type"] = meta.get("content_type", doc.get("content_type"))
            doc["size"] = meta.get("size", doc.get("size"))
            for ex in new_extracts:
                if ex.get("sha256") == meta.get("sha256") and doc.get("group_name"):
                    ex["group_name"] = doc.get("group_name")
    gos["stored_assets"] = stored_assets
    if new_extracts:
        gos["doc_extracts"] = merge_doc_extracts(gos.get("doc_extracts"), new_extracts)
    extras["goszakup"] = gos
    normalized["extras"] = extras
    return normalized


@celery_app.task(name="app.workers.tasks.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="app.workers.tasks.crawl_source", bind=True)
def crawl_source(self, source_code: str = "KZ_GOSZAKUP_OWS_V3") -> dict[str, Any]:
    """Discover → fetch → normalize → upsert into tender-service."""
    adapter = _adapter(source_code)
    if getattr(adapter, "mode", None) == "playwright_stub":
        mode = "playwright_stub"
    elif getattr(adapter, "token", None):
        mode = "live_api"
    else:
        mode = "sample_offline"
    pages_ok = 0
    pages_fail = 0
    pages_skip = 0
    upserted: list[str] = []
    errors: list[str] = []
    skip_reasons: dict[str, int] = {}
    self.update_state(
        state="PROGRESS",
        meta={
            "source_code": source_code,
            "stage": "discover",
            "current": 0,
            "total": 0,
            "percent": 1,
            "message": "Поиск тендеров на портале",
        },
    )

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

    total_refs = len(refs)
    self.update_state(
        state="PROGRESS",
        meta={
            "source_code": source_code,
            "stage": "process",
            "current": 0,
            "total": total_refs,
            "percent": 5 if total_refs else 100,
            "message": f"Найдено тендеров: {total_refs}",
        },
    )

    for idx, ref in enumerate(refs, start=1):
        try:
            raw = adapter.fetch_sync(ref) if hasattr(adapter, "fetch_sync") else None
            if raw is None:
                import asyncio

                raw = asyncio.run(adapter.fetch(ref))
            normalized = adapter.normalize(raw)
            payload = normalized.model_dump(mode="json")
            min_amount = float(os.getenv("GOSZAKUP_PW_FILTER_AMOUNT_FROM") or os.getenv("GOSZAKUP_PW_MIN_AMOUNT") or "0")
            amount = payload.get("amount")
            if min_amount > 0 and amount is not None:
                try:
                    if float(amount) < min_amount:
                        pages_skip += 1
                        skip_reasons["amount_below_min"] = skip_reasons.get("amount_below_min", 0) + 1
                        self.update_state(
                            state="PROGRESS",
                            meta={
                                "source_code": source_code,
                                "stage": "process",
                                "current": idx,
                                "total": total_refs,
                                "pages_ok": pages_ok,
                                "pages_fail": pages_fail,
                                "pages_skip": pages_skip,
                                "percent": min(5 + int((idx / max(total_refs, 1)) * 90), 95),
                                "message": f"{idx}/{total_refs} · skip amount · ok={pages_ok} skip={pages_skip}",
                            },
                        )
                        continue
                except (TypeError, ValueError):
                    pass
            skip_reason = (payload.get("extras") or {}).get("ingest_skip")
            if skip_reason:
                pages_skip += 1
                skip_reasons[str(skip_reason)] = skip_reasons.get(str(skip_reason), 0) + 1
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "source_code": source_code,
                        "stage": "process",
                        "current": idx,
                        "total": total_refs,
                        "pages_ok": pages_ok,
                        "pages_fail": pages_fail,
                        "pages_skip": pages_skip,
                        "percent": min(5 + int((idx / max(total_refs, 1)) * 90), 95),
                        "message": f"{idx}/{total_refs} · skip {skip_reason} · ok={pages_ok} skip={pages_skip}",
                    },
                )
                continue
            payload = _persist_raw_assets(payload)
            market_est = _estimate_market(payload)
            if market_est is not None and not payload.get("market_amount_est"):
                payload["market_amount_est"] = market_est
            result = _upsert_tender(payload)
            upserted.append(result.get("external_id") or normalized.external_id)
            pages_ok += 1
        except Exception as exc:  # noqa: BLE001
            pages_fail += 1
            errors.append(f"{ref}: {exc}")
        percent = 5 + int((idx / max(total_refs, 1)) * 90)
        self.update_state(
            state="PROGRESS",
            meta={
                "source_code": source_code,
                "stage": "process",
                "current": idx,
                "total": total_refs,
                "pages_ok": pages_ok,
                "pages_fail": pages_fail,
                "pages_skip": pages_skip,
                "percent": min(percent, 95),
                "message": f"{idx}/{total_refs} · ok={pages_ok} skip={pages_skip} fail={pages_fail}",
            },
        )

    result = {
        "source_code": source_code,
        "status": "ok" if pages_ok else "empty_or_failed",
        "mode": mode,
        "docs": (
            "https://goszakup.gov.kz/ru/search/announce"
            if mode == "playwright_stub"
            else "https://goszakup.gov.kz/ru/developer/ows_v3"
        ),
        "discovered": len(refs),
        "pages_ok": pages_ok,
        "pages_fail": pages_fail,
        "pages_skip": pages_skip,
        "skip_reasons": skip_reasons,
        "upserted": upserted[:50],
        "errors": errors[:10],
        "task_id": getattr(self.request, "id", None),
    }
    self.update_state(
        state="SUCCESS",
        meta={
            "source_code": source_code,
            "stage": "done",
            "current": total_refs,
            "total": total_refs,
            "pages_ok": pages_ok,
            "pages_fail": pages_fail,
            "pages_skip": pages_skip,
            "skip_reasons": skip_reasons,
            "percent": 100,
            "message": f"Готово: {pages_ok} ok / {pages_skip} skip / {pages_fail} fail",
            "upserted": upserted[:50],
            "errors": errors[:10],
        },
    )
    return result
