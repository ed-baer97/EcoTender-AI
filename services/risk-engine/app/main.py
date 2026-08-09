"""FastAPI entrypoint for risk-engine."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.engine.llm_explain import blend_scores_on_conflict, explain_with_llm_api
from app.engine.scoring import score_tender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("ecotender.risk")

app = FastAPI(title="EcoTender Risk Engine", version="0.3.0")


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

    extras = tender.get("extras") if isinstance(tender.get("extras"), dict) else {}
    cached = extras.get("llm_explain") if isinstance(extras, dict) else None
    if (
        not req.force
        and not extras.get("risk_stale")
        and isinstance(cached, dict)
        and cached.get("text")
        and cached.get("risk_score") is not None
    ):
        logger.info("[score] persisted cache hit tender_id=%s — skip CatBoost/LLM", tender_id)
        score_val = cached.get("risk_score")
        band_val = cached.get("risk_band") or tender.get("risk_band")
        meta = {
            "provider": cached.get("provider"),
            "model": cached.get("model"),
            "prompt_version": cached.get("prompt_version"),
            "source": "cache",
            "evidence_hash": cached.get("evidence_hash"),
            "confidence": cached.get("confidence"),
            "conflict": cached.get("conflict"),
        }
        if cached.get("error"):
            meta["error"] = cached["error"]
        return {
            "tender_id": tender_id,
            "risk_score": score_val,
            "risk_band": band_val,
            "model_risk_score": cached.get("model_risk_score", score_val),
            "model_risk_band": cached.get("model_risk_band", band_val),
            "corruption_proba": None,
            "model_version": None,
            "scored_at": cached.get("scored_at") or datetime.now(timezone.utc).isoformat(),
            "explanation": cached.get("text"),
            "explanation_sections": cached.get("sections") or {},
            "explanation_meta": meta,
            "verdicts": cached.get("verdicts") or {},
            "evidence_summary": cached.get("evidence_summary"),
            "doc_extracts": None,
            "reasons": [],
            "anomalies": [],
            "feature_vector": {},
        }

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
    overprice_driven = any(r.get("code") == "OVERPRICE" for r in result.top_reasons) or bool(
        result.feature_vector.get("market_ignored_reason")
    )
    # If market was ignored but old cached LLM still conflicts — still blend.
    # Also blend when auditor explicitly conflicts with a high model score.
    blended = blend_scores_on_conflict(
        result.risk_score,
        result.risk_band,
        conflict=bool(explanation.conflict),
        auditor_band=explanation.auditor_band,
        overprice_driven=overprice_driven or result.risk_score >= 70,
    )

    logger.info(
        "[score] done tender_id=%s explain_source=%s conflict=%s confidence=%s model=%.1f display=%.1f error=%s",
        tender_id,
        explanation.source,
        blended.get("conflict"),
        blended.get("confidence"),
        result.risk_score,
        blended["risk_score"],
        explanation.error,
    )

    meta: dict[str, Any] = {
        "provider": explanation.provider,
        "model": explanation.model,
        "prompt_version": explanation.prompt_version,
        "source": explanation.source,
        "evidence_hash": explanation.evidence_hash,
        "confidence": blended.get("confidence"),
        "conflict": blended.get("conflict"),
    }
    if explanation.error:
        meta["error"] = explanation.error

    verdicts = {
        "model": {
            "risk_score": blended.get("model_risk_score", result.risk_score),
            "risk_band": blended.get("model_risk_band", result.risk_band),
            "summary": "; ".join(r.get("message_ru", "") for r in result.top_reasons[:2] if r.get("message_ru")),
        },
        "auditor": {
            "risk_band": explanation.auditor_band or result.risk_band,
            "summary": explanation.auditor_summary
            or (explanation.sections.get("verdict") if explanation.sections else None)
            or explanation.text[:180],
            "agree_with_model": explanation.agree_with_model,
        },
        "conflict": bool(blended.get("conflict") or explanation.conflict),
        "confidence": blended.get("confidence") or "high",
    }

    return {
        "tender_id": tender_id,
        "risk_score": blended["risk_score"],
        "risk_band": blended["risk_band"],
        "model_risk_score": blended.get("model_risk_score", result.risk_score),
        "model_risk_band": blended.get("model_risk_band", result.risk_band),
        "corruption_proba": result.corruption_proba,
        "model_version": result.model_version,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "explanation": explanation.text,
        "explanation_sections": explanation.sections or {},
        "explanation_meta": meta,
        "verdicts": verdicts,
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
