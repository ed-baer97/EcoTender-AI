# AI Risk Engine — архитектура

## 1. Гибридная философия

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
│                    OpenAI / DeepSeek / OpenRouter …      │
│                    + template_fallback                   │
│                           │                              │
│                           ▼                              │
│              Human-readable reasons + audit memo         │
└─────────────────────────────────────────────────────────┘

CatBoost = decision  |  LLM = explanation only
```

**Жёсткое правило:** LLM **не** может повысить/понизить score.  
Максимум — запросить `human_review` флаг при низкой уверенности модели.

---

## 2. Признаки (Feature Store v1)

| Feature | Тип | Источник | Описание |
|---------|-----|----------|----------|
| `amount` | float | tender | Сумма тендера (норм. валюта → USD/KZT) |
| `market_amount_est` | float | market-service | Оценка рыночной стоимости работ |
| `overprice_ratio` | float | derived | `amount / market_amount_est` |
| `participants_count` | int | tender | Число участников |
| `single_bidder` | bool | derived | participants == 1 |
| `contractor_wins_2y` | int | contractor stats | Победы за 24 мес |
| `contractor_win_rate` | float | contractor | wins / participations |
| `contractor_same_customer_share` | float | derived | доля побед у одного заказчика |
| `amendments_count` | int | contract | Доп. соглашения |
| `amendment_amount_ratio` | float | derived | сумма дельт / signed_amount |
| `duration_days` | int | tender | Срок исполнения |
| `duration_vs_peer_p50` | float | derived | срок / медиана peеров |
| `area_sq_m` | float | tender/geo | Площадь работ |
| `unit_price_vs_market` | float | work_items | медиана отклонений позиций |
| `region_risk_prior` | float | region stats | историческая доля high-risk |
| `eco_category_oh` | cat | tender | категория (one-hot / CatBoost cat) |
| `procurement_method` | cat | tender | открытый/из одного источника/... |
| `days_to_deadline` | int | tender | окно подачи заявок |
| `published_month` | cat | tender | сезонность |
| `near_protected_area` | bool | geo | пересечение с ООПТ |
| `distance_to_coast_km` | float | geo | до береговой линии |
| `prev_projects_count` | int | contractor | предыдущие эко-проекты |
| `prev_projects_avg_score` | float | risk hist | ср. риск прошлых |

CatBoost нативно принимает категориальные признаки — не нужен ручной one-hot для деревьев.

---

## 3. Архитектура CatBoost

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

Альтернатива для регрессии на continuous label: `CatBoostRegressor` с целевой `risk_label_0_100`, но для cold start удобнее бинарный/ordinal classifier + калибровка.

### Калибровка

```python
from sklearn.calibration import CalibratedClassifierCV
# или ручная isotonic на validation fold
```

Банды: low/medium/high/critical — по калиброванным порогам на validation (не по «красивым» 25/50/75).

---

## 4. Генерация тренировочного датасета без разметки

Проблема: нет официальных меток «коррупционный тендер».

### 4.1 Weak supervision / silver labels

Композиция эвристик → soft label:

| Эвристика | Вес | Условие (пример) |
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
sample_weight = 0.5 + silver  # уверенные эвристики весят больше
```

### 4.2 Синтетика

- Генерация «чистых» тендеров вокруг рыночных цен (negative class)
- Генерация аномалий (positive) контролируемыми сдвигами признаков
- Смешивание 70% real unlabeled + 30% synthetic для устойчивости

### 4.3 Active learning (после хакатона)

UI для аудитора: «согласен / не согласен с риском» → накопление gold set.

### 4.4 Внешние прокси-метки

- Расторгнутые контракты
- Судебные споры / штрафы (если открыты)
- Дисквалификации поставщиков

---

## 5. Pipeline обучения

```text
raw tenders → feature build (ml/features)
           → train/val/test split by time (не random!)
           → CatBoost fit
           → calibration
           → metrics (AUC, PR-AUC, Brier, ECE)
           → SHAP global importance
           → register model_version in DB + artifact MinIO
           → shadow deploy → promote is_active
```

**Time-based split обязателен** (иначе leakage из будущего подрядчика).

```
ml/
  features/build_features.py
  training/train_catboost.py
  training/weak_labels.py
  evaluation/metrics.py
  evaluation/slice_analysis.py   # по регионам/категориям
  models/                        # artifacts
```

---

## 6. Детекция аномалий (поверх модели)

Детерминированные правила — объяснимы и юридически удобны:

1. `PRICE_OUTLIER` — Isolation Forest / z-score по `unit_price` в категории
2. `COLLUSION_PROXY` — одни и те же 2–3 участника ротируют победы
3. `GEO_MISMATCH` — заявленная площадь ≫ геометрии работ
4. `AMENDMENT_SPIKE` — >3 доп. соглашений за первые 20% срока
5. `COAST_ECO_CONFLICT` — high-impact работы внутри buffer ООПТ без EIA ссылки

Аномалии пишутся в `anomaly_flag` и передаются в LLM evidence pack.

---

## 7. LLM Explainer (внешний API, не локальная сеть)

**Схема:** своя CatBoost-модель принимает решение; LLM по API только объясняет.

### Конфиг

```bash
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1   # любой OpenAI-compatible endpoint
LLM_MODEL=gpt-5.6-terra
```

Примеры провайдеров: OpenAI, DeepSeek, OpenRouter, облачный Qwen — достаточно сменить `LLM_BASE_URL` / `LLM_MODEL`.

Код: `services/risk-engine/app/engine/llm_explain.py`  
Ответ API включает `explanation_meta.source` = `llm_api` | `template_fallback`.

### Вход (structured, не свободный текст парсера)

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

### Системный промпт (сжато)

```text
Ты — аналитик госзакупок. Объясни Risk Score простым языком на русском.
Используй ТОЛЬКО факты из JSON. Не обвиняй в преступлениях.
Структура: 1) краткий вывод 2) 3–5 причин 3) рекомендация (мониторинг/аудит).
Максимум 120 слов.
```

### Выход

Сохраняем:
- `explanation_text`
- `reasons[]` → `risk_reason`
- `llm_provider` + `llm_model` + `prompt_version` (воспроизводимость)

### Fallback без API-ключа / при ошибке сети

Шаблоны по кодам аномалий + top features (обязателен для демо офлайн).  
Локальный Ollama **не** используется в MVP.
---

## 8. Метрики качества

| Метрика | Зачем |
|---------|-------|
| ROC-AUC | общее качество ранжирования |
| PR-AUC | при дисбалансе классов |
| Brier score | калибровка вероятностей |
| ECE | calibration curves |
| Recall@top10% | «поймали ли мы рисковые в топе» — важно для аудиторов |
| Slice AUC | по стране/категории — поиск bias |

Онлайн (после запуска):
- Agreement rate с аудитором
- Explanation usefulness (thumbs)
- Drift: PSI / KS по признакам

---

## 9. API внутри risk-engine

```
POST /v1/score          {tender_id} | {feature_vector}
POST /v1/score/batch    {tender_ids[]}
GET  /v1/assessments/{tender_id}
POST /v1/explain        {assessment_id}   # idempotent if exists
GET  /v1/models         active + history
```

Score endpoint синхронный для single; batch — через Celery.

---

## 10. Переход на собственную нейросеть

Когда данных ≥ 50k размеченных / слабо размеченных:

| Этап | Модель | Вход |
|------|--------|------|
| v1 | CatBoost | tabular |
| v2 | TabNet / FT-Transformer | tabular + embeddings |
| v3 | Two-tower | contractor graph emb + tender text emb |
| v4 | Multimodal | + satellite patch CNN + PDF text |

План миграции без ломки API:
1. `model_registry.algorithm` = `catboost` | `ft_transformer` | ...
2. Один интерфейс `Predictor.predict(features) -> ScoreResult`
3. A/B shadow: оба скорят, в UI только active
4. LLM explainer продолжает работать от feature+shap-like attributions (Integrated Gradients)

```python
class Predictor(Protocol):
    version: str
    def predict(self, df: pd.DataFrame) -> ScoreResult: ...
```

---

## 11. Безопасность AI-контура

- Нет PII в промптах к публичному API (минимум полей)
- Rate limit explain
- Prompt injection: tender description truncate + strip instructions
- Ключ только в env (`LLM_API_KEY`), никогда в git
- Логируем provider/model/prompt_version + hash промпта, не полный текст в public logs
