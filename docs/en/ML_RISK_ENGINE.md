**Language:** [Русский](../ru/ML_RISK_ENGINE.md) · [English](ML_RISK_ENGINE.md) · [Қазақша](../kk/ML_RISK_ENGINE.md)

# AI Risk Engine — Architecture

## 1. Hybrid Philosophy

```text
┌─────────────────────────────────────────────────────────┐
│                    RISK ENGINE                           │
│                                                          │
│  Features ──► CatBoost ──► risk_score (0..100)           │
│       │            │                                     │
│       │            ▼                                     │
│       │      Anomaly rules (deterministic)               │
│       │            │                                     │
│       └────────────┼──────────────┐                      │
│                    ▼              ▼                      │
│              SHAP / top feats   Evidence pack            │
│                    └──────┬───────┘                      │
│                           ▼                              │
│                    LLM Explainer (external API)          │
│                    OpenAI / DeepSeek / Qwen 3.8 Max / OpenRouter …      │
│                    + template_fallback                   │
│                           │                              │
│                           ▼                              │
│              Human-readable reasons + audit memo         │
└─────────────────────────────────────────────────────────┘

CatBoost = decision  |  LLM = explanation only
```

**Hard rule:** the LLM **cannot** raise/lower the score.  
At most — request a `human_review` flag when model confidence is low.

---

## 2. Features (Feature Store v1)

| Feature | Type | Source | Description |
|---------|------|--------|-------------|
| `amount` | float | tender | Tender amount (norm. currency → USD/KZT) |
| `market_amount_est` | float | market-service | Estimated market cost of works |
| `overprice_ratio` | float | derived | `amount / market_amount_est` |
| `participants_count` | int | tender | Number of participants |
| `single_bidder` | bool | derived | participants == 1 |
| `contractor_wins_2y` | int | contractor stats | Wins over 24 months |
| `contractor_win_rate` | float | contractor | wins / participations |
| `contractor_same_customer_share` | float | derived | share of wins with one customer |
| `amendments_count` | int | contract | Amendments |
| `amendment_amount_ratio` | float | derived | sum of deltas / signed_amount |
| `duration_days` | int | tender | Execution duration |
| `duration_vs_peer_p50` | float | derived | duration / peer median |
| `area_sq_m` | float | tender/geo | Work area |
| `unit_price_vs_market` | float | work_items | median line-item deviations |
| `region_risk_prior` | float | region stats | historical high-risk share |
| `eco_category_oh` | cat | tender | category (one-hot / CatBoost cat) |
| `procurement_method` | cat | tender | open / single source / … |
| `days_to_deadline` | int | tender | bid submission window |
| `published_month` | cat | tender | seasonality |
| `near_protected_area` | bool | geo | intersection with protected area |
| `distance_to_coast_km` | float | geo | to coastline |
| `prev_projects_count` | int | contractor | previous eco-projects |
| `prev_projects_avg_score` | float | risk hist | avg. risk of past ones |

CatBoost natively accepts categorical features — no manual one-hot needed for trees.

---

## 3. CatBoost Architecture

```python
from catboost import CatBoostClassifier, Pool

FEATURE_COLS = [
    "amount_log", "overprice_ratio", "participants_count",
    "contractor_wins_2y", "contractor_win_rate",
    "amendments_count", "amendment_amount_ratio",
    "duration_days", "duration_vs_peer_p50", "area_sq_m_log",
    "unit_price_vs_market", "region_risk_prior",
    "days_to_deadline", "near_protected_area",
    "distance_to_coast_km", "prev_projects_count",
    "prev_projects_avg_score", "single_bidder",
]

CAT_COLS = ["eco_category", "procurement_method", "region_code", "country_code"]

model = CatBoostClassifier(
    loss_function="Logloss",
    eval_metric="AUC",
    depth=6,
    learning_rate=0.05,
    l2_leaf_reg=3.0,
    iterations=800,
    random_seed=42,
    early_stopping_rounds=50,
    auto_class_weights="Balanced",
    cat_features=CAT_COLS,
)

# Inference
proba = model.predict_proba(X)[:, 1]          # P(high_corruption_risk)
risk_score = (proba * 100).clip(0, 100)       # 0..100
```

Alternative for regression on a continuous label: `CatBoostRegressor` with target `risk_label_0_100`, but for cold start a binary/ordinal classifier + calibration is more convenient.

### Calibration

```python
from sklearn.calibration import CalibratedClassifierCV
# or manual isotonic on validation fold
```

Bands: low/medium/high/critical — by calibrated thresholds on validation (not by “pretty” 25/50/75).

---

## 4. Generating a Training Dataset Without Labels

Problem: there are no official “corrupt tender” labels.

### 4.1 Weak Supervision / Silver Labels

Composition of heuristics → soft label:

| Heuristic | Weight | Condition (example) |
|-----------|--------|---------------------|
| H1 overprice | 0.25 | overprice_ratio > 1.4 |
| H2 single bidder | 0.20 | participants_count <= 1 |
| H3 repeat winner | 0.15 | contractor_win_rate > 0.7 & wins_2y >= 5 |
| H4 amendments | 0.15 | amendment_amount_ratio > 0.25 |
| H5 short window | 0.10 | days_to_deadline < 7 |
| H6 peer outlier | 0.15 | amount > region_cat_p95 |

```python
silver = (
    0.25 * (overprice > 1.4)
  + 0.20 * (participants <= 1)
  + 0.15 * ((win_rate > 0.7) & (wins >= 5))
  + 0.15 * (amend_ratio > 0.25)
  + 0.10 * (days_to_deadline < 7)
  + 0.15 * (amount > p95)
)
y_bin = (silver >= 0.45).astype(int)
sample_weight = 0.5 + silver  # confident heuristics weigh more
```

### 4.2 Synthetic Data

- Generate “clean” tenders around market prices (negative class)
- Generate anomalies (positive) with controlled feature shifts
- Mix 70% real unlabeled + 30% synthetic for robustness

### 4.3 Active Learning (Post-Hackathon)

Auditor UI: “agree / disagree with risk” → accumulate gold set.

### 4.4 External Proxy Labels

- Terminated contracts
- Court disputes / fines (if open)
- Supplier disqualifications

---

## 5. Training Pipeline

```text
raw tenders → feature build (ml/features)
           → train/val/test split by time (not random!)
           → CatBoost fit
           → calibration
           → metrics (AUC, PR-AUC, Brier, ECE)
           → SHAP global importance
           → register model_version in DB + artifact MinIO
           → shadow deploy → promote is_active
```

**Time-based split is mandatory** (otherwise leakage from future contractor).

```
ml/
  features/build_features.py
  training/train_catboost.py
  training/weak_labels.py
  evaluation/metrics.py
  evaluation/slice_analysis.py   # by region/category
  models/                        # artifacts
```

---

## 6. Anomaly Detection (On Top of the Model)

Deterministic rules — explainable and legally convenient:

1. `PRICE_OUTLIER` — Isolation Forest / z-score on `unit_price` in category
2. `COLLUSION_PROXY` — the same 2–3 participants rotate wins
3. `GEO_MISMATCH` — declared area ≫ work geometry
4. `AMENDMENT_SPIKE` — >3 amendments in the first 20% of the term
5. `COAST_ECO_CONFLICT` — high-impact works inside protected-area buffer without EIA reference

Anomalies are written to `anomaly_flag` and passed into the LLM evidence pack.

---

## 7. LLM Explainer (External API, Not a Local Network)

**Scheme:** own CatBoost model makes the decision; LLM via API only explains.

### Config

```bash
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1   # any OpenAI-compatible endpoint
LLM_MODEL=gpt-5.6-terra
```

Example providers: OpenAI, DeepSeek, **Qwen 3.8 Max** (`qwen3.8-max` via DashScope compatible-mode), OpenRouter — enough to change `LLM_BASE_URL` / `LLM_MODEL` / key.

Code: `services/risk-engine/app/engine/llm_explain.py`  
API response includes `explanation_meta.source` = `llm_api` | `template_fallback`.

### Input (structured, not free-form parser text)

```json
{
  "tender_id": "...",
  "title": "Shoreline cleanup — Aktau",
  "risk_score": 78,
  "risk_band": "high",
  "top_features": [
    {"name": "overprice_ratio", "value": 1.47, "shap": 0.22},
    {"name": "participants_count", "value": 1, "shap": 0.18}
  ],
  "anomalies": ["PRICE_OUTLIER", "SINGLE_BIDDER"],
  "disclaimer": "Analytical indicator, not a legal conclusion"
}
```

### System Prompt (condensed)

```text
You are a public procurement analyst. Explain the Risk Score in plain language in Russian.
Use ONLY facts from the JSON. Do not accuse of crimes.
Structure: 1) brief verdict 2) 3–5 reasons 3) recommendation (monitoring/audit).
Maximum 120 words.
```

### Output

We store:
- `explanation_text`
- `reasons[]` → `risk_reason`
- `llm_provider` + `llm_model` + `prompt_version` (reproducibility)

### Fallback Without API Key / on Network Error

Templates by anomaly codes + top features (required for offline demo).  
Local Ollama is **not** used in the MVP.
---

## 8. Quality Metrics

| Metric | Why |
|--------|-----|
| ROC-AUC | overall ranking quality |
| PR-AUC | under class imbalance |
| Brier score | probability calibration |
| ECE | calibration curves |
| Recall@top10% | “did we catch risky ones in the top” — important for auditors |
| Slice AUC | by country/category — bias search |

Online (after launch):
- Agreement rate with auditor
- Explanation usefulness (thumbs)
- Drift: PSI / KS on features

---

## 9. API Inside risk-engine

```
POST /v1/score          {tender_id} | {feature_vector}
POST /v1/score/batch    {tender_ids[]}
GET  /v1/assessments/{tender_id}
POST /v1/explain        {assessment_id}   # idempotent if exists
GET  /v1/models         active + history
```

Score endpoint is synchronous for single; batch — via Celery.

---

## 10. Path to Own Neural Network

When data ≥ 50k labeled / weakly labeled:

| Stage | Model | Input |
|-------|-------|-------|
| v1 | CatBoost | tabular |
| v2 | TabNet / FT-Transformer | tabular + embeddings |
| v3 | Two-tower | contractor graph emb + tender text emb |
| v4 | Multimodal | + satellite patch CNN + PDF text |

Migration plan without breaking the API:
1. `model_registry.algorithm` = `catboost` | `ft_transformer` | ...
2. One interface `Predictor.predict(features) -> ScoreResult`
3. A/B shadow: both score, UI shows only active
4. LLM explainer keeps working from feature+shap-like attributions (Integrated Gradients)

```python
class Predictor(Protocol):
    version: str
    def predict(self, df: pd.DataFrame) -> ScoreResult: ...
```

---

## 11. AI Contour Security

- No PII in prompts to public API (minimum fields)
- Rate limit explain
- Prompt injection: tender description truncate + strip instructions
- Key only in env (`LLM_API_KEY`), never in git
- Log provider/model/prompt_version + prompt hash, not full text in public logs
