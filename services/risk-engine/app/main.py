"""FastAPI entrypoint for risk-engine."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.engine.llm_explain import explain_with_llm_api
from app.engine.scoring import score_tender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("ecotender.risk")

app = FastAPI(title="EcoTender Risk Engine", version="0.2.0")


class ScoreRequest(BaseModel):
    tender_id: UUID | None = None
    title: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    force: bool = False


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "risk-engine"}


@app.post("/v1/score")
async def score(req: ScoreRequest) -> dict[str, Any]:
    tender = dict(req.features or {})
    tender_id = str(req.tender_id) if req.tender_id else (str(tender.get("id")) if tender.get("id") else None)
    title = req.title or str(tender.get("title") or "")
    logger.info("[score] start tender_id=%s title=%r force=%s", tender_id, title[:80], req.force)

    # Fast path: return cached CatBoost+LLM bundle when hash still valid is handled inside explain;
    # CatBoost itself is cheap — always refresh score so band/chips stay current.
    result = score_tender(tender)
    logger.info(
        "[score] catboost tender_id=%s score=%.1f band=%s model=%s",
        tender_id,
        result.risk_score,
        result.risk_band,
        result.model_version,
    )

    amount = None
    if tender.get("amount") not in (None, ""):
        try:
            amount = float(tender["amount"])
        except (TypeError, ValueError):
            amount = None

    explanation = await explain_with_llm_api(
        result,
        title=title,
        tender_id=tender_id,
        amount=amount,
        currency=str(tender.get("currency") or "KZT"),
        tender=tender,
        force=req.force,
    )
    logger.info(
        "[score] done tender_id=%s explain_source=%s provider=%s model=%s hash=%s error=%s",
        tender_id,
        explanation.source,
        explanation.provider,
        explanation.model,
        explanation.evidence_hash,
        explanation.error,
    )

    meta: dict[str, Any] = {
        "provider": explanation.provider,
        "model": explanation.model,
        "prompt_version": explanation.prompt_version,
        "source": explanation.source,
        "evidence_hash": explanation.evidence_hash,
    }
    if explanation.error:
        meta["error"] = explanation.error

    return {
        "tender_id": tender_id,
        "risk_score": result.risk_score,
        "risk_band": result.risk_band,
        "corruption_proba": result.corruption_proba,
        "model_version": result.model_version,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "explanation": explanation.text,
        "explanation_meta": meta,
        "evidence_summary": {
            "docs": len((explanation.evidence or {}).get("doc_extracts") or []),
            "gaps": (explanation.evidence or {}).get("gaps") or [],
            "kv_keys": len(((explanation.evidence or {}).get("portal") or {}).get("kv") or {}),
        },
        "doc_extracts": explanation.doc_extracts_to_persist,
        "reasons": result.top_reasons,
        "anomalies": [
            {"anomaly_type": a.anomaly_type, "severity": a.severity, "evidence": a.evidence}
            for a in result.anomalies
        ],
        "feature_vector": result.feature_vector,
    }
