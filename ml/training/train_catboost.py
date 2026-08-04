"""Train CatBoost risk model from fixtures + weak labels.

Usage:
  pip install catboost pandas scikit-learn
  python ml/training/train_catboost.py --fixtures data/fixtures/tenders.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd


def weak_label(row: dict) -> tuple[int, float]:
    amount = float(row.get("amount") or 0)
    market = float(row.get("market_amount_est") or amount or 1)
    overprice = amount / market if market else 1.0
    participants = int(row.get("participants_count") or 0)
    win_rate = float(row.get("contractor_win_rate") or 0)
    wins = int(row.get("contractor_wins_2y") or 0)
    amend = float(row.get("amendment_amount_ratio") or 0)

    silver = 0.0
    silver += 0.25 * (1.0 if overprice > 1.4 else 0.0)
    silver += 0.20 * (1.0 if participants <= 1 else 0.0)
    silver += 0.15 * (1.0 if win_rate > 0.7 and wins >= 5 else 0.0)
    silver += 0.15 * (1.0 if amend > 0.25 else 0.0)
    silver += 0.10 * (1.0 if participants <= 2 else 0.0)
    silver += 0.15 * (1.0 if overprice > 1.25 else 0.0)
    y = 1 if silver >= 0.45 else 0
    return y, 0.5 + silver


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    records = []
    for row in rows:
        amount = float(row.get("amount") or 0)
        market = float(row.get("market_amount_est") or amount or 1)
        y, w = weak_label(row)
        records.append(
            {
                "amount_log": math.log1p(amount),
                "overprice_ratio": amount / market if market else 1.0,
                "participants_count": int(row.get("participants_count") or 0),
                "contractor_wins_2y": int(row.get("contractor_wins_2y") or 0),
                "contractor_win_rate": float(row.get("contractor_win_rate") or 0),
                "amendments_count": int(row.get("amendments_count") or 0),
                "amendment_amount_ratio": float(row.get("amendment_amount_ratio") or 0),
                "duration_days": int(row.get("duration_days") or 0),
                "area_sq_m_log": math.log1p(float(row.get("area_sq_m") or 0)),
                "single_bidder": 1 if int(row.get("participants_count") or 0) <= 1 else 0,
                "eco_category": row.get("eco_category") or "other",
                "procurement_method": row.get("procurement_method") or "unknown",
                "region_code": row.get("region_code") or "UNK",
                "country_code": row.get("country_code") or "XX",
                "y": y,
                "sample_weight": w,
            }
        )
    return pd.DataFrame(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("ml/models/catboost_risk_v1.cbm"))
    args = parser.parse_args()

    rows = json.loads(args.fixtures.read_text(encoding="utf-8"))
    df = rows_to_frame(rows)

    # Expand tiny fixture set with controlled synthetics for a trainable demo model
    synth = []
    for i in range(80):
        base = rows[i % len(rows)].copy()
        base["amount"] = float(base.get("amount") or 1e8) * (0.7 + (i % 7) * 0.15)
        base["participants_count"] = 1 + (i % 5)
        base["amendment_amount_ratio"] = (i % 6) * 0.08
        base["contractor_win_rate"] = 0.2 + (i % 8) * 0.1
        base["contractor_wins_2y"] = i % 10
        synth.append(base)
    df = pd.concat([df, rows_to_frame(synth)], ignore_index=True)

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

    try:
        from catboost import CatBoostClassifier, Pool
    except ImportError:
        meta = {
            "status": "catboost_not_installed",
            "rows": len(df),
            "positive_rate": float(df["y"].mean()),
            "message": "Install catboost to export .cbm; heuristic scorer remains available in risk-engine.",
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(json.dumps(meta, indent=2))
        return

    X = df[feature_cols + cat_cols]
    y = df["y"]
    w = df["sample_weight"]
    pool = Pool(X, y, weight=w, cat_features=cat_cols)
    model = CatBoostClassifier(
        loss_function="Logloss",
        eval_metric="AUC",
        depth=4,
        learning_rate=0.08,
        iterations=200,
        verbose=False,
        random_seed=42,
        auto_class_weights="Balanced",
    )
    model.fit(pool)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(args.out))
    meta = {
        "version": "catboost-v1",
        "artifact": str(args.out),
        "rows": len(df),
        "positive_rate": float(y.mean()),
        "features": feature_cols + cat_cols,
    }
    args.out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
