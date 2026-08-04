"""Risk Engine — CatBoost decision + rule anomalies + LLM/template explanation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ecotender_shared.enums import AnomalyType, score_to_band


FEATURE_DEFAULTS = {
    "amount_log": 0.0,
    "overprice_ratio": 1.0,
    "participants_count": 3,
    "contractor_wins_2y": 0,
    "contractor_win_rate": 0.3,
    "amendments_count": 0,
    "amendment_amount_ratio": 0.0,
    "duration_days": 180,
    "area_sq_m_log": 0.0,
    "single_bidder": 0,
}


@dataclass
class Anomaly:
    anomaly_type: str
    severity: float
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoreResult:
    risk_score: float
    corruption_proba: float
    risk_band: str
    feature_vector: dict[str, Any]
    anomalies: list[Anomaly]
    top_reasons: list[dict[str, Any]]
    model_version: str


def build_features(raw: dict[str, Any]) -> dict[str, Any]:
    amount = float(raw.get("amount") or 0.0)
    market = float(raw.get("market_amount_est") or amount or 1.0)
    participants = int(raw.get("participants_count") or 0)
    overprice = amount / market if market > 0 else 1.0
    area = float(raw.get("area_sq_m") or 0.0)

    return {
        "amount_log": math.log1p(amount),
        "overprice_ratio": overprice,
        "participants_count": participants,
        "contractor_wins_2y": int(raw.get("contractor_wins_2y") or 0),
        "contractor_win_rate": float(raw.get("contractor_win_rate") or 0.0),
        "amendments_count": int(raw.get("amendments_count") or 0),
        "amendment_amount_ratio": float(raw.get("amendment_amount_ratio") or 0.0),
        "duration_days": int(raw.get("duration_days") or 0),
        "area_sq_m_log": math.log1p(area),
        "single_bidder": 1 if participants <= 1 else 0,
        "eco_category": raw.get("eco_category") or "other",
        "procurement_method": raw.get("procurement_method") or "unknown",
        "region_code": raw.get("region_code") or "UNK",
        "country_code": raw.get("country_code") or "XX",
    }


def detect_anomalies(features: dict[str, Any]) -> list[Anomaly]:
    out: list[Anomaly] = []
    if features["overprice_ratio"] >= 1.35:
        out.append(
            Anomaly(
                AnomalyType.PRICE_OUTLIER.value,
                min(1.0, (features["overprice_ratio"] - 1.0)),
                {"overprice_ratio": features["overprice_ratio"]},
            )
        )
    if features["single_bidder"]:
        out.append(Anomaly(AnomalyType.SINGLE_BIDDER.value, 0.85, {"participants_count": features["participants_count"]}))
    if features["contractor_win_rate"] >= 0.7 and features["contractor_wins_2y"] >= 5:
        out.append(
            Anomaly(
                AnomalyType.REPEAT_WINNER.value,
                0.75,
                {
                    "contractor_win_rate": features["contractor_win_rate"],
                    "contractor_wins_2y": features["contractor_wins_2y"],
                },
            )
        )
    if features["amendment_amount_ratio"] >= 0.25:
        out.append(
            Anomaly(
                AnomalyType.AMENDMENT_SPIKE.value,
                min(1.0, features["amendment_amount_ratio"]),
                {"amendment_amount_ratio": features["amendment_amount_ratio"]},
            )
        )
    return out


def heuristic_proba(features: dict[str, Any]) -> float:
    """Cold-start scorer used until CatBoost artifact is trained.

    Mirrors weak-supervision weights — replace with model.predict_proba in production.
    """
    score = 0.0
    score += 0.25 * (1.0 if features["overprice_ratio"] > 1.4 else max(0.0, (features["overprice_ratio"] - 1.0) / 0.4))
    score += 0.20 * features["single_bidder"]
    score += 0.15 * (1.0 if features["contractor_win_rate"] > 0.7 and features["contractor_wins_2y"] >= 5 else features["contractor_win_rate"] * 0.5)
    score += 0.15 * min(1.0, features["amendment_amount_ratio"] / 0.25)
    score += 0.10 * (1.0 if features["participants_count"] <= 2 else 0.0)
    score += 0.15 * min(1.0, max(0.0, features["overprice_ratio"] - 1.0))
    return max(0.0, min(1.0, score))


_MODEL_CACHE: dict[str, Any] = {}


def _predict_proba(features: dict[str, Any]) -> tuple[float, str]:
    """Prefer CatBoost artifact; fall back to heuristic."""
    import os
    from pathlib import Path

    model_path = Path(os.getenv("MODEL_PATH", "/models/catboost_risk_v1.cbm"))
    if not model_path.exists():
        alt = Path(__file__).resolve().parents[4] / "ml" / "models" / "catboost_risk_v1.cbm"
        model_path = alt if alt.exists() else model_path

    if model_path.exists():
        try:
            key = str(model_path)
            if key not in _MODEL_CACHE:
                from catboost import CatBoostClassifier

                model = CatBoostClassifier()
                model.load_model(str(model_path))
                _MODEL_CACHE[key] = model
            model = _MODEL_CACHE[key]
            feature_cols = [
                "amount_log",
                "overprice_ratio",
                "participants_count",
                "contractor_wins_2y",
                "contractor_win_rate",
                "amendments_count",
                "amendment_amount_ratio",
                "duration_days",
                "area_sq_m_log",
                "single_bidder",
            ]
            cat_cols = ["eco_category", "procurement_method", "region_code", "country_code"]
            row = {k: features.get(k) for k in feature_cols + cat_cols}
            import pandas as pd

            proba = float(model.predict_proba(pd.DataFrame([row]))[0][1])
            return proba, "catboost-v1"
        except Exception:
            pass
    return heuristic_proba(features), "heuristic-v1"


def score_tender(raw: dict[str, Any], model_version: str | None = None) -> ScoreResult:
    features = build_features(raw)
    anomalies = detect_anomalies(features)
    proba, detected_version = _predict_proba(features)
    model_version = model_version or detected_version
    # Slight boost from stacked anomalies (still capped)
    proba = min(1.0, proba + 0.03 * len(anomalies))
    risk_score = round(proba * 100, 1)
    band = score_to_band(risk_score).value

    reasons: list[dict[str, Any]] = []
    if features["overprice_ratio"] > 1.1:
        pct = int((features["overprice_ratio"] - 1.0) * 100)
        reasons.append(
            {
                "code": "OVERPRICE",
                "severity": "high" if pct >= 35 else "medium",
                "message_ru": f"Стоимость превышает рыночную на {pct}%.",
                "contribution": 0.25,
            }
        )
    if features["single_bidder"]:
        reasons.append(
            {
                "code": "SINGLE_BIDDER",
                "severity": "high",
                "message_ru": "Количество участников минимальное (единственная заявка).",
                "contribution": 0.2,
            }
        )
    if features["contractor_win_rate"] >= 0.7:
        reasons.append(
            {
                "code": "REPEAT_WINNER",
                "severity": "medium",
                "message_ru": "Подрядчик регулярно выигрывает аналогичные тендеры.",
                "contribution": 0.15,
            }
        )
    if features["amendment_amount_ratio"] >= 0.2:
        reasons.append(
            {
                "code": "AMENDMENTS",
                "severity": "medium",
                "message_ru": "Существенный рост суммы через дополнительные соглашения.",
                "contribution": 0.15,
            }
        )
    if not reasons:
        reasons.append(
            {
                "code": "BASELINE",
                "severity": "low",
                "message_ru": "Существенных ценовых и процедурных аномалий не выявлено.",
                "contribution": 0.05,
            }
        )

    return ScoreResult(
        risk_score=risk_score,
        corruption_proba=proba,
        risk_band=band,
        feature_vector=features,
        anomalies=anomalies,
        top_reasons=reasons,
        model_version=model_version,
    )


def template_explain(result: ScoreResult, title: str = "") -> str:
    head = f"Проект «{title}». " if title else ""
    body = " ".join(r["message_ru"] for r in result.top_reasons[:4])
    if result.risk_score >= 60:
        tail = " Проект рекомендуется для проведения аудита."
    elif result.risk_score >= 30:
        tail = " Рекомендуется усиленный мониторинг исполнения."
    else:
        tail = " Существенных оснований для приоритетного аудита нет."
    return f"{head}Risk Score: {result.risk_score:.0f}/100 ({result.risk_band}). {body}{tail}"
