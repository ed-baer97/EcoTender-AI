**Тіл / Language:** [Русский](../ru/ML_RISK_ENGINE.md) · [English](../en/ML_RISK_ENGINE.md) · [Қазақша](ML_RISK_ENGINE.md)

# AI Risk Engine — архитектура

## 1. Гибридті философия

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

**Қатаң ереже:** LLM score-ты **көтере немесе төмендете алмайды**.  
Максимум — модель сенімі төмен болғанда `human_review` флагін сұрау.

---

## 2. Белгілер (Feature Store v1)

| Feature | Түрі | Көзі | Сипаттама |
|---------|-----|----------|----------|
| `amount` | float | tender | Тендер сомасы (норм. валюта → USD/KZT) |
| `market_amount_est` | float | market-service | Жұмыстардың нарықтық құнын бағалау |
| `overprice_ratio` | float | derived | `amount / market_amount_est` |
| `participants_count` | int | tender | Қатысушылар саны |
| `single_bidder` | bool | derived | participants == 1 |
| `contractor_wins_2y` | int | contractor stats | 24 айдағы жеңістер |
| `contractor_win_rate` | float | contractor | wins / participations |
| `contractor_same_customer_share` | float | derived | бір тапсырыс берушідегі жеңістер үлесі |
| `amendments_count` | int | contract | Қосымша келісімдер |
| `amendment_amount_ratio` | float | derived | дельталар сомасы / signed_amount |
| `duration_days` | int | tender | Орындау мерзімі |
| `duration_vs_peer_p50` | float | derived | мерзім / peer медианасы |
| `area_sq_m` | float | tender/geo | Жұмыс ауданы |
| `unit_price_vs_market` | float | work_items | позиция ауытқуларының медианасы |
| `region_risk_prior` | float | region stats | high-risk тарихи үлесі |
| `eco_category_oh` | cat | tender | санат (one-hot / CatBoost cat) |
| `procurement_method` | cat | tender | ашық/бір көзден/... |
| `days_to_deadline` | int | tender | өтінім беру терезесі |
| `published_month` | cat | tender | маусымдылық |
| `near_protected_area` | bool | geo | ЕҚТА-мен қиылысу |
| `distance_to_coast_km` | float | geo | жағалау сызығына дейін |
| `prev_projects_count` | int | contractor | алдыңғы эко-жобалар |
| `prev_projects_avg_score` | float | risk hist | өткен орташа тәуекел |

CatBoost категориялық белгілерді тума қабылдайды — ағаштар үшін қолмен one-hot қажет емес.

---

## 3. CatBoost архитектурасы

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

Continuous label үшін регрессия альтернативасы: `risk_label_0_100` мақсаты бар `CatBoostRegressor`, бірақ cold start үшін бинарлы/ordinal classifier + калибрлеу ыңғайлырақ.

### Калибрлеу

```python
from sklearn.calibration import CalibratedClassifierCV
# немесе validation fold-та қолмен isotonic
```

Band-тар: low/medium/high/critical — validation-дағы калибрленген шектер бойынша («әдемі» 25/50/75 емес).

---

## 4. Белгілеусіз тренировкалық датасет генерациясы

Мәселе: «сыбайлас жемқорлық тендері» ресми белгілері жоқ.

### 4.1 Weak supervision / silver labels

Эвристикалар композициясы → soft label:

| Эвристика | Салмақ | Шарт (мысал) |
|-----------|-----|------------------|
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
sample_weight = 0.5 + silver  # сенімді эвристикалар көбірек салмақ алады
```

### 4.2 Синтетика

- Нарықтық бағалар айналасында «таза» тендерлер генерациясы (negative class)
- Белгілерді басқарылатын ығысулармен аномалиялар генерациясы (positive)
- Тұрақтылық үшін 70% real unlabeled + 30% synthetic араластыру

### 4.3 Active learning (хакатоннан кейін)

Аудитор үшін UI: «тәуекелмен келісемін / келіспеймін» → gold set жинау.

### 4.4 Сыртқы прокси-белгілер

- Бұзылған шарттар
- Сот даулары / айыппұлдар (ашық болса)
- Жеткізушілерді дисквалификациялау

---

## 5. Оқыту pipeline

```text
raw tenders → feature build (ml/features)
           → train/val/test split by time (random емес!)
           → CatBoost fit
           → calibration
           → metrics (AUC, PR-AUC, Brier, ECE)
           → SHAP global importance
           → register model_version in DB + artifact MinIO
           → shadow deploy → promote is_active
```

**Time-based split міндетті** (әйтпесе болашақ мердігерден leakage).

```
ml/
  features/build_features.py
  training/train_catboost.py
  training/weak_labels.py
  evaluation/metrics.py
  evaluation/slice_analysis.py   # өңірлер/санаттар бойынша
  models/                        # artifacts
```

---

## 6. Аномалияларды анықтау (модель үстінен)

Детерминистік ережелер — түсіндіріледі және заңдық тұрғыдан ыңғайлы:

1. `PRICE_OUTLIER` — категориядағы `unit_price` бойынша Isolation Forest / z-score
2. `COLLUSION_PROXY` — сол 2–3 қатысушы жеңістерді айналдырады
3. `GEO_MISMATCH` — мәлімделген аудан ≫ жұмыс геометриясы
4. `AMENDMENT_SPIKE` — мерзімнің алғашқы 20%-ында >3 қосымша келісім
5. `COAST_ECO_CONFLICT` — EIA сілтемесі жоқ ЕҚТА buffer ішіндегі high-impact жұмыстар

Аномалиялар `anomaly_flag`-қа жазылады және LLM evidence pack-ке беріледі.

---

## 7. LLM Explainer (сыртқы API, жергілікті желі емес)

**Схема:** өз CatBoost-моделі шешім қабылдайды; LLM API арқылы тек түсіндіреді.

### Конфиг

```bash
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1   # кез келген OpenAI-compatible endpoint
LLM_MODEL=gpt-5.6-terra
```

Провайдер мысалдары: OpenAI, DeepSeek, **Qwen 3.8 Max** (`qwen3.8-max` DashScope compatible-mode арқылы), OpenRouter — `LLM_BASE_URL` / `LLM_MODEL` / кілтті өзгерту жеткілікті.

Код: `services/risk-engine/app/engine/llm_explain.py`  
API жауабында `explanation_meta.source` = `llm_api` | `template_fallback`.

### Кіріс (structured, парсердің еркін мәтіні емес)

```json
{
  "tender_id": "...",
  "title": "Очистка береговой линии — Актау",
  "risk_score": 78,
  "risk_band": "high",
  "top_features": [
    {"name": "overprice_ratio", "value": 1.47, "shap": 0.22},
    {"name": "participants_count", "value": 1, "shap": 0.18}
  ],
  "anomalies": ["PRICE_OUTLIER", "SINGLE_BIDDER"],
  "disclaimer": "Аналитический индикатор, не юридический вывод"
}
```

### Жүйелік промпт (қысқартылған)

```text
Ты — аналитик госзакупок. Объясни Risk Score простым языком на русском.
Используй ТОЛЬКО факты из JSON. Не обвиняй в преступлениях.
Структура: 1) краткий вывод 2) 3–5 причин 3) рекомендация (мониторинг/аудит).
Максимум 120 слов.
```

### Шығыс

Сақтаймыз:
- `explanation_text`
- `reasons[]` → `risk_reason`
- `llm_provider` + `llm_model` + `prompt_version` (қайталанушылық)

### API-кілтсіз / желі қатесінде fallback

Аномалия кодтары + top features бойынша шаблондар (офлайн демо үшін міндетті).  
Жергілікті Ollama MVP-де **қолданылмайды**.
---

## 8. Сапа метрикалары

| Метрика | Не үшін |
|---------|-------|
| ROC-AUC | жалпы ранжирлеу сапасы |
| PR-AUC | класс теңгерімсіздігінде |
| Brier score | ықтималдықтарды калибрлеу |
| ECE | calibration curves |
| Recall@top10% | «тәуекелділерді топта ұстадық па» — аудиторлар үшін маңызды |
| Slice AUC | ел/санат бойынша — bias іздеу |

Онлайн (іске қосылғаннан кейін):
- Аудитормен agreement rate
- Explanation usefulness (thumbs)
- Drift: белгілер бойынша PSI / KS

---

## 9. risk-engine ішіндегі API

```
POST /v1/score          {tender_id} | {feature_vector}
POST /v1/score/batch    {tender_ids[]}
GET  /v1/assessments/{tender_id}
POST /v1/explain        {assessment_id}   # idempotent if exists
GET  /v1/models         active + history
```

Score endpoint single үшін синхронды; batch — Celery арқылы.

---

## 10. Өз нейрондық желіге өту

Деректер ≥ 50k белгіленген / әлсіз белгіленген болғанда:

| Кезең | Модель | Кіріс |
|------|--------|------|
| v1 | CatBoost | tabular |
| v2 | TabNet / FT-Transformer | tabular + embeddings |
| v3 | Two-tower | contractor graph emb + tender text emb |
| v4 | Multimodal | + satellite patch CNN + PDF text |

API-ны бұзбай көшу жоспары:
1. `model_registry.algorithm` = `catboost` | `ft_transformer` | ...
2. Бір интерфейс `Predictor.predict(features) -> ScoreResult`
3. A/B shadow: екеуі де скорлайды, UI-да тек active
4. LLM explainer feature+shap-like attributions-тан жұмысын жалғастырады (Integrated Gradients)

```python
class Predictor(Protocol):
    version: str
    def predict(self, df: pd.DataFrame) -> ScoreResult: ...
```

---

## 11. AI-контур қауіпсіздігі

- Ашық API промпттарында PII жоқ (өрістер минимумы)
- Rate limit explain
- Prompt injection: tender description truncate + strip instructions
- Кілт тек env-де (`LLM_API_KEY`), ешқашан git-те емес
- provider/model/prompt_version + промпт hash-ін логтаймыз, public logs-та толық мәтін емес
