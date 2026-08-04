"""FastAPI entrypoint for risk-engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.engine.llm_explain import explain_with_llm_api
from app.engine.scoring import score_tender

app = FastAPI(title="EcoTender Risk Engine", version="0.1.0")


class ScoreRequest(BaseModel):
    tender_id: UUID | None = None
    title: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "risk-engine"}


@app.post("/v1/score")
async def score(req: ScoreRequest) -> dict[str, Any]:
    result = score_tender(req.features)
    explanation = await explain_with_llm_api(
        result,
        title=req.title or "",
        tender_id=str(req.tender_id) if req.tender_id else None,
    )
    return {
        "tender_id": str(req.tender_id) if req.tender_id else None,
        "risk_score": result.risk_score,
        "risk_band": result.risk_band,
        "corruption_proba": result.corruption_proba,
        "model_version": result.model_version,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "explanation": explanation.text,
        "explanation_meta": {
            "provider": explanation.provider,
            "model": explanation.model,
            "prompt_version": explanation.prompt_version,
            "source": explanation.source,
        },
        "reasons": result.top_reasons,
        "anomalies": [
            {"anomaly_type": a.anomaly_type, "severity": a.severity, "evidence": a.evidence}
            for a in result.anomalies
        ],
        "feature_vector": result.feature_vector,
    }
