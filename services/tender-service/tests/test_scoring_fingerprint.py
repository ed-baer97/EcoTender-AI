"""Unit tests for risk-preservation fingerprint (no DB)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repository import scoring_fingerprint  # noqa: E402


def _base(**overrides):
    row = {
        "title": "Очистка побережья",
        "amount": 1_000_000,
        "currency": "KZT",
        "participants_count": 2,
        "winner_name": "ТОО Eco",
        "procurement_method": "open_tender",
        "market_amount_est": 900_000,
        "amendments_count": 0,
        "amendment_amount_ratio": 0,
        "contractor_wins_2y": 1,
        "contractor_win_rate": 0.2,
        "eco_category": "coastal_cleanup",
        "region_code": "KZ-MAN",
        "extras": {
            "goszakup": {
                "lots": [{"id": 1}],
                "documents": [{"name": "TZ.pdf", "url": "/a"}],
                "protocols": [],
                "contracts": [],
                "status": "published",
            }
        },
    }
    row.update(overrides)
    return row


def test_fingerprint_stable_for_identical_payload():
    a = scoring_fingerprint(_base())
    b = scoring_fingerprint(_base())
    assert a == b
    assert len(a) == 24


def test_fingerprint_ignores_llm_explain_noise():
    a = scoring_fingerprint(_base())
    noisy = _base()
    noisy["extras"] = {
        **noisy["extras"],
        "llm_explain": {"text": "x", "risk_score": 77},
        "raw_html": "<html>changed</html>",
    }
    assert scoring_fingerprint(noisy) == a


def test_fingerprint_changes_on_amount():
    a = scoring_fingerprint(_base())
    b = scoring_fingerprint(_base(amount=2_000_000))
    assert a != b


def test_fingerprint_changes_on_new_document():
    a = scoring_fingerprint(_base())
    changed = _base()
    changed["extras"]["goszakup"]["documents"].append({"name": "Dogovor.pdf", "url": "/b"})
    assert scoring_fingerprint(changed) != a
