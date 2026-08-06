"""Unit checks for market confidence gating and structured LLM explain."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow importing scoring without full FastAPI app package path hacks in CI.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# shared package for score_to_band
SHARED = Path(__file__).resolve().parents[3] / "packages" / "shared"
sys.path.insert(0, str(SHARED))

from app.engine.scoring import build_features, score_tender  # noqa: E402
from app.engine.llm_explain import (  # noqa: E402
    blend_scores_on_conflict,
    format_explain_text,
    parse_llm_payload,
    parse_sections_from_plain_text,
)
from app.engine.scoring import ScoreResult  # noqa: E402


def test_weak_fuzzy_market_does_not_inflate_overprice():
    raw = {
        "amount": 26_000_000,
        "market_amount_est": 1_000_000,
        "market_match_confidence": 0.35,
        "title": "Страхование",
        "extras": {},
    }
    feats = build_features(raw)
    assert feats["has_market_est"] == 0
    assert feats["overprice_ratio"] == 1.0
    assert feats["market_ignored_reason"] == "low_match_confidence"
    assert feats["overprice_ratio_raw"] == 26.0


def test_absurd_ratio_without_confidence_ignored():
    raw = {
        "amount": 50_000_000,
        "market_amount_est": 1_000_000,
        "extras": {},
    }
    feats = build_features(raw)
    assert feats["has_market_est"] == 0
    assert feats["market_ignored_reason"] in {"low_match_confidence", "absurd_overprice_ratio"}


def test_strong_hint_market_keeps_overprice():
    raw = {
        "amount": 1_800_000,
        "market_amount_est": 1_000_000,
        "market_match_confidence": 0.65,
        "extras": {},
    }
    feats = build_features(raw)
    assert feats["has_market_est"] == 1
    assert abs(feats["overprice_ratio"] - 1.8) < 1e-6


def test_parse_plain_sections_wall_of_text():
    text = (
        "A) Вердикт: Риск критический (84.3/100). Модель указывает на завышение, "
        "однако документы опровергают это: экономия 22%. "
        "B) Подтверждения из документов: План 10 млн. Факт 7.8 млн. Экономия 22%. "
        "C) Пробелы данных: Нет спецификации. "
        "D) Рекомендация: мониторинг"
    )
    sections = parse_sections_from_plain_text(text)
    assert "экономия" in sections["verdict"].lower() or "критическ" in sections["verdict"].lower()
    assert sections.get("recommendation")
    formatted = format_explain_text(sections)
    assert "\n\n" in formatted
    assert "A) Вердикт" in formatted


def test_parse_json_payload_and_blend():
    result = ScoreResult(
        risk_score=84.3,
        corruption_proba=0.843,
        risk_band="critical",
        feature_vector={},
        anomalies=[],
        top_reasons=[{"code": "OVERPRICE", "message_ru": "x"}],
        model_version="test",
    )
    raw = """{
      "conflict": true,
      "agree_with_model": false,
      "auditor_band": "low",
      "auditor_summary": "Документы показывают экономию, не переплату",
      "sections": {
        "verdict": "Риск низкий: экономия 22%.",
        "evidence": ["План выше факта", "Договор исполнен"],
        "gaps": ["Нет полного ТЗ"],
        "recommendation": "мониторинг"
      }
    }"""
    parsed = parse_llm_payload(raw, result)
    assert parsed.conflict is True
    assert parsed.auditor_band == "low"
    assert "•" in parsed.text
    blended = blend_scores_on_conflict(
        84.3,
        "critical",
        conflict=True,
        auditor_band="low",
        overprice_driven=True,
    )
    assert blended["conflict"] is True
    assert blended["confidence"] == "low"
    assert blended["risk_score"] < 84.3
    assert blended["risk_score"] < 40


def test_score_tender_no_overprice_reason_when_market_weak():
    scored = score_tender(
        {
            "amount": 26_000_000,
            "market_amount_est": 1_000_000,
            "market_match_confidence": 0.3,
            "title": "Аренда",
            "extras": {"goszakup": {}},
        }
    )
    codes = {r["code"] for r in scored.top_reasons}
    assert "OVERPRICE" not in codes
