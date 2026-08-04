"""LLM explainer via external API (OpenAI-compatible).

CatBoost owns the score. LLM only narrates evidence.
Falls back to deterministic templates when API key/network is unavailable.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from app.engine.scoring import ScoreResult, template_explain

PROMPT_VERSION = "explain-v1-ru"


SYSTEM_PROMPT = """Ты — аналитик государственных закупок и экологических проектов Каспия.
Объясни Risk Score простым языком на русском.
Используй ТОЛЬКО факты из JSON. Не обвиняй в преступлениях и не выдумывай факты.
Структура ответа: 1) краткий вывод 2) 3–5 причин 3) рекомендация (мониторинг или аудит).
Максимум 120 слов. Без markdown-заголовков."""


@dataclass
class ExplainResult:
    text: str
    provider: str
    model: str
    prompt_version: str
    source: str  # "llm_api" | "template_fallback"


def _llm_config() -> dict[str, str | None]:
    return {
        "provider": os.getenv("LLM_PROVIDER", "openai"),
        "api_key": os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
        "base_url": (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
        "model": os.getenv("LLM_MODEL", "gpt-5.6-terra"),
    }


def build_evidence_pack(result: ScoreResult, title: str = "", tender_id: str | None = None) -> dict[str, Any]:
    return {
        "tender_id": tender_id,
        "title": title,
        "risk_score": result.risk_score,
        "risk_band": result.risk_band,
        "model_version": result.model_version,
        "top_features": [
            {"name": k, "value": v}
            for k, v in list(result.feature_vector.items())[:12]
            if not isinstance(v, str) or k in {"eco_category", "procurement_method", "region_code", "country_code"}
        ],
        "reasons": result.top_reasons,
        "anomalies": [
            {"anomaly_type": a.anomaly_type, "severity": a.severity, "evidence": a.evidence}
            for a in result.anomalies
        ],
        "disclaimer": "Аналитический индикатор, не юридический вывод",
    }


async def explain_with_llm_api(result: ScoreResult, title: str = "", tender_id: str | None = None) -> ExplainResult:
    cfg = _llm_config()
    fallback = ExplainResult(
        text=template_explain(result, title),
        provider=str(cfg["provider"] or "none"),
        model=str(cfg["model"] or "none"),
        prompt_version=PROMPT_VERSION,
        source="template_fallback",
    )

    if not cfg["api_key"]:
        return fallback

    evidence = build_evidence_pack(result, title=title, tender_id=tender_id)
    payload = {
        "model": cfg["model"],
        "temperature": 0.2,
        "max_tokens": 280,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Сформируй объяснение по данным:\n" + json.dumps(evidence, ensure_ascii=False),
            },
        ],
    }

    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if not text:
                return fallback
            return ExplainResult(
                text=text,
                provider=str(cfg["provider"]),
                model=str(data.get("model") or cfg["model"]),
                prompt_version=PROMPT_VERSION,
                source="llm_api",
            )
    except Exception:
        return fallback
