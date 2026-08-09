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


SENSITIVE_ECO = {
    "oil_spill_response",
    "dredging",
    "reclamation",
    "shore_protection",
    "coastal_cleanup",
}

# Market fixture match must be at least "hint" quality before overprice affects score.
MARKET_CONFIDENCE_MIN = 0.55
# Ratios this extreme usually mean wrong SKU / unit mismatch, not real overprice.
ABSURD_OVERPRICE_RATIO = 8.0


def _resolve_market_confidence(raw: dict[str, Any]) -> float | None:
    if raw.get("market_match_confidence") not in (None, ""):
        try:
            return float(raw["market_match_confidence"])
        except (TypeError, ValueError):
            pass
    extras = raw.get("extras") or {}
    me = extras.get("market_estimate") if isinstance(extras, dict) else None
    if isinstance(me, dict) and me.get("confidence") not in (None, ""):
        try:
            return float(me["confidence"])
        except (TypeError, ValueError):
            pass
    return None


def _market_estimate_usable(
    amount: float,
    market: float,
    confidence: float | None,
) -> tuple[bool, str | None]:
    """Gate weak / irrelevant market matches so they cannot inflate risk."""
    if market <= 0:
        return False, "no_market"
    over = amount / market if market > 0 else 1.0
    # Legacy rows without confidence: distrust extreme ratios.
    conf = confidence if confidence is not None else 0.4
    if conf < MARKET_CONFIDENCE_MIN:
        return False, "low_match_confidence"
    if over >= ABSURD_OVERPRICE_RATIO and conf < 0.9:
        return False, "absurd_overprice_ratio"
    if over >= 20.0:
        return False, "absurd_overprice_ratio"
    return True, None


def build_features(raw: dict[str, Any]) -> dict[str, Any]:
    extras = raw.get("extras") or {}
    gos = extras.get("goszakup") or {}
    lots = gos.get("lots") or []
    bidders = gos.get("bidders") or []
    protocols = gos.get("protocols") or []
    contracts = gos.get("contracts") or []
    documents = gos.get("documents") or []
    tab_stats = gos.get("raw_tab_stats") or {}
    amount = float(raw.get("amount") or 0.0)
    market_raw = raw.get("market_amount_est")
    market_conf = _resolve_market_confidence(raw)
    has_raw_market = market_raw not in (None, "", 0, 0.0)
    market_val = float(market_raw) if has_raw_market else 0.0
    raw_overprice = (amount / market_val) if (has_raw_market and market_val > 0) else 1.0
    usable, ignore_reason = _market_estimate_usable(amount, market_val, market_conf) if has_raw_market else (False, None)
    overprice = raw_overprice if usable else 1.0
    parts_raw = raw.get("participants_count")
    participants = int(parts_raw) if parts_raw not in (None, "") else (-1 if not bidders else len(bidders))
    area = float(raw.get("area_sq_m") or 0.0)
    # True single bidder only when explicitly one participant — missing ≠ single.
    single_bidder = 1 if participants == 1 else 0

    return {
        "amount_log": math.log1p(amount),
        "amount": amount,
        "overprice_ratio": overprice,
        "overprice_ratio_raw": raw_overprice if has_raw_market else None,
        "market_match_confidence": market_conf,
        "market_ignored_reason": ignore_reason,
        "participants_count": max(0, participants),
        "participants_known": 1 if participants >= 0 else 0,
        "contractor_wins_2y": int(raw.get("contractor_wins_2y") or 0),
        "contractor_win_rate": float(raw.get("contractor_win_rate") or 0.0),
        "amendments_count": int(raw.get("amendments_count") or 0),
        "amendment_amount_ratio": float(raw.get("amendment_amount_ratio") or 0.0),
        "duration_days": int(raw.get("duration_days") or 0),
        "area_sq_m_log": math.log1p(area),
        "single_bidder": single_bidder,
        "eco_category": raw.get("eco_category") or "other",
        "procurement_method": raw.get("procurement_method") or "unknown",
        "region_code": raw.get("region_code") or "UNK",
        "country_code": raw.get("country_code") or "XX",
        "has_market_est": 1 if usable else 0,
        "lots_count": len(lots),
        "documents_count": len(documents),
        "protocols_count": len(protocols),
        "contracts_count": len(contracts),
        "tabs_count": int(tab_stats.get("tabs_count") or len(gos.get("tabs") or [])),
        "has_winner": 1 if raw.get("winner_name") else 0,
        "has_protocols": 1 if protocols else 0,
        "has_contracts": 1 if contracts else 0,
    }


def detect_anomalies(features: dict[str, Any]) -> list[Anomaly]:
    out: list[Anomaly] = []
    if features["has_market_est"] and features["overprice_ratio"] >= 1.35:
        out.append(
            Anomaly(
                AnomalyType.PRICE_OUTLIER.value,
                min(1.0, (features["overprice_ratio"] - 1.0)),
                {"overprice_ratio": features["overprice_ratio"]},
            )
        )
    if features["single_bidder"]:
        out.append(Anomaly(AnomalyType.SINGLE_BIDDER.value, 0.85, {"participants_count": features["participants_count"]}))
    method = str(features.get("procurement_method") or "")
    if method == "single_source":
        out.append(
            Anomaly(
                AnomalyType.SINGLE_BIDDER.value,
                0.7,
                {"procurement_method": method},
            )
        )
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
    if features.get("documents_count", 0) == 0:
        out.append(Anomaly(AnomalyType.COAST_ECO_CONFLICT.value, 0.25, {"documents_count": 0}))
    return out


def heuristic_proba(features: dict[str, Any]) -> float:
    """Rule-based scorer — primary for sparse live portal data, fallback for CatBoost.

    Differentiates by amount, method, competition, eco sensitivity and contractor history.
    """
    score = 0.08  # baseline floor so "clean" tenders are not all identical zeros
    amount = float(features.get("amount") or 0.0)
    method = str(features.get("procurement_method") or "")
    eco = str(features.get("eco_category") or "other")
    parts = int(features.get("participants_count") or 0)
    parts_known = bool(features.get("participants_known"))

    # Price vs market (only when market estimate exists)
    if features.get("has_market_est"):
        over = float(features["overprice_ratio"])
        score += 0.22 * (1.0 if over > 1.4 else max(0.0, (over - 1.0) / 0.4))
        score += 0.12 * min(1.0, max(0.0, over - 1.0))

    # Competition / procedure
    if features["single_bidder"]:
        score += 0.22
    elif parts_known and 0 < parts <= 2:
        score += 0.12
    elif not parts_known:
        score += 0.06  # opacity: participants unknown from portal scrape

    if method == "single_source":
        score += 0.28
    elif method == "request_price":
        score += 0.10
    elif method == "auction":
        score += 0.04

    # Contractor concentration
    wr = float(features["contractor_win_rate"])
    wins = int(features["contractor_wins_2y"])
    if wr > 0.7 and wins >= 5:
        score += 0.18
    else:
        score += 0.08 * wr

    # Amendments
    score += 0.14 * min(1.0, float(features["amendment_amount_ratio"]) / 0.25)

    # Amount magnitude (large eco contracts warrant higher scrutiny)
    if amount >= 1_000_000_000:
        score += 0.18
    elif amount >= 100_000_000:
        score += 0.12
    elif amount >= 10_000_000:
        score += 0.08
    elif amount >= 1_000_000:
        score += 0.04
    elif amount > 0 and amount < 100_000:
        score -= 0.02

    # Sensitive eco categories (Caspian / oil spill / dredging)
    if eco in SENSITIVE_ECO:
        score += 0.10
    if eco == "oil_spill_response":
        score += 0.06

    region = str(features.get("region_code") or "")
    if region in ("KZ-MAN", "KZ-ATY") and eco in SENSITIVE_ECO:
        score += 0.05
    if int(features.get("lots_count") or 0) >= 3:
        score += 0.05
    if int(features.get("documents_count") or 0) == 0:
        score += 0.05
    if int(features.get("protocols_count") or 0) == 0:
        score += 0.04
    if int(features.get("contracts_count") or 0) > 0:
        score += 0.05

    return max(0.0, min(1.0, score))


def _features_sparse(features: dict[str, Any]) -> bool:
    """Live scrape often lacks market/contractor/amendment signals."""
    rich_bits = 0
    if features.get("has_market_est"):
        rich_bits += 1
    if features.get("contractor_wins_2y"):
        rich_bits += 1
    if features.get("amendments_count") or features.get("amendment_amount_ratio"):
        rich_bits += 1
    if features.get("participants_known") and features.get("participants_count", 0) > 0:
        rich_bits += 1
    if features.get("duration_days"):
        rich_bits += 1
    return rich_bits < 2


_MODEL_CACHE: dict[str, Any] = {}


def _resolve_model_path() -> Path:
    """Resolve CatBoost artifact path without assuming a fixed repo depth (breaks in Docker)."""
    import os
    from pathlib import Path

    configured = Path(os.getenv("MODEL_PATH", "/models/catboost_risk_v1.cbm"))
    candidates = [configured]
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "ml" / "models" / "catboost_risk_v1.cbm")
        candidates.append(parent / "models" / "catboost_risk_v1.cbm")
    for path in candidates:
        try:
            if path.exists():
                return path
        except OSError:
            continue
    return configured


def _predict_proba(features: dict[str, Any]) -> tuple[float, str]:
    """Prefer CatBoost artifact; fall back to heuristic."""
    model_path = _resolve_model_path()

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
    model_proba, detected_version = _predict_proba(features)
    heur = heuristic_proba(features)

    # Sparse live portal rows: CatBoost was trained on rich fixtures and collapses
    # everything to ~same low score — prefer differentiated heuristic.
    if _features_sparse(features):
        proba = max(heur, 0.35 * model_proba + 0.65 * heur)
        version = f"heuristic-v2+{detected_version}"
    else:
        proba = 0.55 * model_proba + 0.45 * heur
        version = detected_version

    model_version = model_version or version
    proba = min(1.0, proba + 0.04 * len(anomalies))
    risk_score = round(proba * 100, 1)
    band = score_to_band(risk_score).value

    reasons: list[dict[str, Any]] = []
    method = str(features.get("procurement_method") or "")
    eco = str(features.get("eco_category") or "")
    amount = float(features.get("amount") or 0.0)

    if method == "single_source":
        reasons.append(
            {
                "code": "SINGLE_SOURCE",
                "severity": "high",
                "message_ru": "Закупка из одного источника — ограниченная конкуренция.",
                "contribution": 0.28,
            }
        )
    if features.get("has_market_est") and features["overprice_ratio"] > 1.1:
        pct = int((features["overprice_ratio"] - 1.0) * 100)
        reasons.append(
            {
                "code": "OVERPRICE",
                "severity": "high" if pct >= 35 else "medium",
                "message_ru": f"Стоимость превышает рыночную на {pct}%.",
                "contribution": 0.25,
            }
        )
    elif features.get("market_ignored_reason"):
        reasons.append(
            {
                "code": "MARKET_ESTIMATE_WEAK",
                "severity": "low",
                "message_ru": (
                    "Рыночная оценка отключена: слабый/нерелевантный match каталога "
                    f"({features.get('market_ignored_reason')})."
                ),
                "contribution": 0.0,
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
    elif not features.get("participants_known"):
        reasons.append(
            {
                "code": "OPAQUE_COMPETITION",
                "severity": "low",
                "message_ru": "Число участников на портале не указано — прозрачность ограничена.",
                "contribution": 0.06,
            }
        )
    elif 0 < features["participants_count"] <= 2:
        reasons.append(
            {
                "code": "LOW_COMPETITION",
                "severity": "medium",
                "message_ru": f"Низкая конкуренция: {features['participants_count']} участника(ов).",
                "contribution": 0.12,
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
    if amount >= 100_000_000:
        reasons.append(
            {
                "code": "LARGE_CONTRACT",
                "severity": "medium",
                "message_ru": f"Крупный контракт: {amount:,.0f} KZT — повышенный приоритет мониторинга.".replace(",", " "),
                "contribution": 0.1,
            }
        )
    if eco in SENSITIVE_ECO:
        reasons.append(
            {
                "code": "ECO_SENSITIVE",
                "severity": "medium",
                "message_ru": f"Чувствительная эко-категория: {eco}.",
                "contribution": 0.1,
            }
        )
    if method == "request_price" and amount >= 1_000_000:
        reasons.append(
            {
                "code": "PRICE_REQUEST",
                "severity": "low",
                "message_ru": "Запрос ценовых предложений при существенной сумме.",
                "contribution": 0.08,
            }
        )
    if int(features.get("lots_count") or 0) >= 3:
        reasons.append(
            {
                "code": "MULTI_LOT_SCOPE",
                "severity": "low",
                "message_ru": f"Многолотовая закупка: {features['lots_count']} лота(ов), требуется детальная проверка разбивки.",
                "contribution": 0.05,
            }
        )
    if int(features.get("documents_count") or 0) == 0:
        reasons.append(
            {
                "code": "NO_DOCS",
                "severity": "medium",
                "message_ru": "На публичной карточке не найдены документы закупки.",
                "contribution": 0.05,
            }
        )
    if int(features.get("protocols_count") or 0) == 0:
        reasons.append(
            {
                "code": "NO_PROTOCOLS",
                "severity": "low",
                "message_ru": "Не найдены итоговые протоколы или результаты по вкладкам.",
                "contribution": 0.04,
            }
        )
    elif not features.get("has_winner"):
        reasons.append(
            {
                "code": "NO_WINNER",
                "severity": "low",
                "message_ru": "Результаты есть, но победитель не распознан автоматически.",
                "contribution": 0.04,
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
        top_reasons=reasons[:5],
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
