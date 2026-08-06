"""LLM explainer via external API (OpenAI-compatible).

Pipeline: CatBoost (layer 1) → Evidence Pack (structured + docs) → Qwen (layer 2).
Falls back to deterministic templates when API key/network is unavailable.
Caches by evidence_hash so docs are never re-fed raw to the model.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.engine.scoring import ScoreResult, template_explain

PROMPT_VERSION = "explain-v3-evidence-docs"
logger = logging.getLogger("ecotender.llm")


def _mask_key(api_key: str | None) -> str:
    if not api_key:
        return "(empty)"
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:3]}…{api_key[-4:]}"


SYSTEM_PROMPT = """Ты — внешний аудитор госзакупок Казахстана (Каспий / Мангистау).
Тебе дан JSON Evidence Pack: слой внутренней модели (CatBoost/heuristic) + факты портала + выдержки из скачанных документов.

Правила:
1) Используй ТОЛЬКО факты из JSON. Не выдумывай суммы, даты, победителей, пункты ТЗ.
2) Валюта: currency из JSON. Для KZT — «тенге»/KZT. Запрещено писать «рублей/руб», если currency ≠ RUB.
3) Слой модели (risk_score, reasons, anomalies) — опорный индикатор; сверь его с документами и KV. Если модель и документы расходятся — явно укажи расхождение.
4) Документы: опирайся на doc_extracts; если excerpt обрезан или error — скажи, что данных не хватает.
5) Не обвиняй в преступлениях; формулируй как аналитический риск.

Структура ответа (русский, ≤180 слов, без markdown-заголовков):
A) Вердикт: score/band своими словами + 1 фраза «почему».
B) Подтверждения из документов/KV (3–5 пунктов).
C) Пробелы данных / что проверить вручную.
D) Рекомендация: мониторинг | углублённый аудит | приоритетный аудит."""


@dataclass
class ExplainResult:
    text: str
    provider: str
    model: str
    prompt_version: str
    source: str  # "llm_api" | "template_fallback" | "cache"
    error: str | None = None
    evidence_hash: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    doc_extracts_to_persist: list[dict[str, Any]] | None = None


def _llm_config() -> dict[str, str | None]:
    try:
        from ecotender_shared.runtime_secrets import get_active_llm_raw, get_config_value

        active = get_active_llm_raw()
        if active:
            return {
                "provider": active.get("provider") or "openai",
                "api_key": active.get("api_key") or os.getenv("OPENAI_API_KEY"),
                "base_url": (active.get("base_url") or "https://api.openai.com/v1").rstrip("/"),
                "model": active.get("model") or "gpt-5.6-terra",
            }
    except ImportError:  # pragma: no cover
        get_config_value = lambda key, default=None: os.getenv(key, default)  # type: ignore[assignment]

    return {
        "provider": get_config_value("LLM_PROVIDER", "openai") or "openai",
        "api_key": get_config_value("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
        "base_url": (get_config_value("LLM_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1").rstrip(
            "/"
        ),
        "model": get_config_value("LLM_MODEL", "gpt-5.6-terra") or "gpt-5.6-terra",
    }


def _currency_label(code: str) -> str:
    c = (code or "KZT").upper()
    return {"KZT": "тенге", "RUB": "рублей", "USD": "долларов США", "EUR": "евро"}.get(c, c)


def _trim_kv(kv: dict[str, Any] | None, limit: int = 20) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, (k, v) in enumerate((kv or {}).items()):
        if i >= limit:
            break
        val = str(v).strip()
        if not val:
            continue
        out[str(k)[:120]] = val[:400]
    return out


def _top_list(items: list[dict[str, Any]] | None, keys: list[str], limit: int = 8) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in (items or [])[:limit]:
        row = {k: item.get(k) for k in keys if item.get(k) not in (None, "", [])}
        if row:
            out.append(row)
    return out


def _build_gaps(tender: dict[str, Any], gos: dict[str, Any], extracts: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    if tender.get("participants_count") in (None, "", 0):
        gaps.append("participants_count_missing")
    docs = gos.get("documents") or []
    if not docs:
        gaps.append("no_documents_on_portal")
    elif not any(e.get("excerpt") for e in extracts):
        gaps.append("no_document_text_extracted")
    if any(d.get("download_error") for d in docs):
        gaps.append("some_document_download_errors")
    if not any(
        (e.get("kind") == "specification")
        or "спецификац" in str(e.get("group_name") or "").lower()
        or "спецификац" in str(e.get("name") or "").lower()
        for e in extracts + docs
    ):
        gaps.append("no_specification_detected")
    if not (gos.get("bidders") or []):
        gaps.append("no_bidders_tab")
    if not (gos.get("protocols") or []):
        gaps.append("no_protocols")
    if tender.get("winner_name") in (None, ""):
        gaps.append("winner_unknown")
    return gaps


def portal_announce_url(external_id: str | None) -> str | None:
    if not external_id:
        return None
    # external_id often like "17438930-1" — announce id before dash
    announce_id = str(external_id).split("-")[0]
    if announce_id.isdigit():
        return f"https://goszakup.gov.kz/ru/announce/index/{announce_id}"
    return None


def hash_evidence(pack: dict[str, Any]) -> str:
    canonical = json.dumps(pack, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def build_evidence_pack(
    result: ScoreResult,
    tender: dict[str, Any] | None = None,
    *,
    title: str = "",
    tender_id: str | None = None,
    amount: float | None = None,
    currency: str = "KZT",
) -> dict[str, Any]:
    tender = tender or {}
    extras = tender.get("extras") or {}
    gos = extras.get("goszakup") if isinstance(extras.get("goszakup"), dict) else {}
    if not isinstance(gos, dict):
        gos = {}

    # Lazy MinIO extract when ingest didn't populate excerpts yet.
    extracts_updated = False
    try:
        from ecotender_shared.doc_extract import ensure_doc_extracts_from_minio, rank_doc_extracts

        before = len(gos.get("doc_extracts") or [])
        if gos.get("documents"):
            filled = ensure_doc_extracts_from_minio(gos)
            if filled != (gos.get("doc_extracts") or []):
                gos = {**gos, "doc_extracts": filled}
                extracts_updated = True
            elif not any((e or {}).get("excerpt") for e in (gos.get("doc_extracts") or [])) and filled:
                gos = {**gos, "doc_extracts": filled}
                extracts_updated = len(filled) > before
        ranked_docs = rank_doc_extracts(gos.get("doc_extracts") or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[llm] doc extract unavailable: %s", exc)
        ranked_docs = []
        for item in (gos.get("doc_extracts") or [])[:5]:
            ranked_docs.append(
                {
                    "name": item.get("name"),
                    "kind": item.get("kind"),
                    "group_name": item.get("group_name"),
                    "chars": item.get("chars"),
                    "truncated": item.get("truncated"),
                    "excerpt": str(item.get("excerpt") or "")[:3500],
                    **({"error": item["error"]} if item.get("error") else {}),
                }
            )
        extracts_updated = False

    cur = (currency or tender.get("currency") or "KZT").upper()
    amt = amount if amount is not None else tender.get("amount")
    if amt is None:
        amt = result.feature_vector.get("amount")

    identity = {
        "tender_id": tender_id or tender.get("id"),
        "external_id": tender.get("external_id") or extras.get("goszakup_id") or extras.get("number_anno"),
        "title": title or tender.get("title") or "",
        "portal_url": portal_announce_url(str(tender.get("external_id") or extras.get("goszakup_id") or "")),
        "amount": amt,
        "currency": cur,
        "currency_label_ru": _currency_label(cur),
        "region_code": tender.get("region_code"),
        "region_name": tender.get("region_name"),
        "procurement_method": tender.get("procurement_method"),
        "customer_name": tender.get("customer_name"),
        "eco_category": tender.get("eco_category"),
        "deadline_at": tender.get("deadline_at"),
        "status_label": extras.get("status_label"),
    }

    model_layer = {
        "risk_score": result.risk_score,
        "risk_band": result.risk_band,
        "model_version": result.model_version,
        "reasons": result.top_reasons,
        "anomalies": [
            {"anomaly_type": a.anomaly_type, "severity": a.severity, "evidence": a.evidence}
            for a in result.anomalies
        ],
        "key_features": [
            {"name": k, "value": v}
            for k, v in list(result.feature_vector.items())[:12]
            if not isinstance(v, str) or k in {"eco_category", "procurement_method", "region_code", "country_code"}
        ],
    }

    portal = {
        "kv": _trim_kv(gos.get("kv")),
        "lots": _top_list(gos.get("lots"), ["name", "amount", "lot_number"], 8),
        "bidders": _top_list(gos.get("bidders"), ["name", "identifier", "status"], 8),
        "protocols": _top_list(gos.get("protocols"), ["winner_name", "status"], 5),
        "contracts": _top_list(gos.get("contracts"), ["name", "supplier", "amount"], 5),
        "documents_meta": _top_list(
            gos.get("documents"),
            ["name", "kind", "group_name", "content_type", "size", "download_error"],
            12,
        ),
        "raw_tab_stats": gos.get("raw_tab_stats") or {},
    }

    pack = {
        "identity": identity,
        "amount_note": f"Суммы указывай только в {_currency_label(cur)} ({cur}), не в рублях.",
        "model_layer": model_layer,
        "portal": portal,
        "doc_extracts": ranked_docs,
        "gaps": _build_gaps(tender, gos, gos.get("doc_extracts") or []),
        "disclaimer": "Аналитический индикатор, не юридический вывод",
        "prompt_version": PROMPT_VERSION,
        "_doc_extracts_full": gos.get("doc_extracts") if extracts_updated else None,
    }
    return pack


def cached_explain_from_extras(
    extras: dict[str, Any] | None,
    *,
    evidence_hash: str,
    result: ScoreResult,
    title: str,
) -> ExplainResult | None:
    cache = (extras or {}).get("llm_explain") if isinstance(extras, dict) else None
    if not isinstance(cache, dict):
        return None
    if cache.get("evidence_hash") != evidence_hash:
        return None
    text = str(cache.get("text") or "").strip()
    if not text:
        return None
    return ExplainResult(
        text=text,
        provider=str(cache.get("provider") or "cache"),
        model=str(cache.get("model") or "cache"),
        prompt_version=str(cache.get("prompt_version") or PROMPT_VERSION),
        source="cache",
        evidence_hash=evidence_hash,
    )


async def explain_with_llm_api(
    result: ScoreResult,
    title: str = "",
    tender_id: str | None = None,
    *,
    amount: float | None = None,
    currency: str = "KZT",
    tender: dict[str, Any] | None = None,
    force: bool = False,
) -> ExplainResult:
    cfg = _llm_config()
    provider = str(cfg["provider"] or "none")
    model = str(cfg["model"] or "none")
    base_url = str(cfg["base_url"] or "")
    tender = tender or {}

    evidence = build_evidence_pack(
        result,
        tender,
        title=title,
        tender_id=tender_id,
        amount=amount,
        currency=currency,
    )
    doc_extracts_to_persist = evidence.pop("_doc_extracts_full", None)
    ehash = hash_evidence(evidence)

    fallback = ExplainResult(
        text=template_explain(result, title),
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        source="template_fallback",
        evidence_hash=ehash,
        evidence=evidence,
        doc_extracts_to_persist=doc_extracts_to_persist if isinstance(doc_extracts_to_persist, list) else None,
    )

    if not force:
        cached = cached_explain_from_extras(
            tender.get("extras") if isinstance(tender.get("extras"), dict) else None,
            evidence_hash=ehash,
            result=result,
            title=title,
        )
        if cached:
            cached.evidence = evidence
            cached.doc_extracts_to_persist = (
                doc_extracts_to_persist if isinstance(doc_extracts_to_persist, list) else None
            )
            logger.info(
                "[llm] explain CACHE HIT tender_id=%s hash=%s",
                tender_id,
                ehash,
            )
            return cached

    if not cfg["api_key"]:
        fallback.error = "llm_api_key_missing"
        logger.warning(
            "[llm] skip explain tender_id=%s reason=api_key_missing provider=%s model=%s",
            tender_id,
            provider,
            model,
        )
        return fallback

    payload = {
        "model": cfg["model"],
        "temperature": 0.2,
        "max_tokens": 420,
        "enable_thinking": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Сформируй разбор по Evidence Pack:\n" + json.dumps(evidence, ensure_ascii=False),
            },
        ],
    }

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    logger.info(
        "[llm] explain start tender_id=%s provider=%s model=%s key=%s score=%.1f docs=%s hash=%s force=%s",
        tender_id,
        provider,
        model,
        _mask_key(str(cfg["api_key"])),
        result.risk_score,
        len(evidence.get("doc_extracts") or []),
        ehash,
        force,
    )
    started = time.perf_counter()
    timeout = httpx.Timeout(90.0, connect=10.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if resp.status_code >= 400:
                try:
                    err_body = resp.json()
                    err = err_body.get("error") or err_body
                except Exception:  # noqa: BLE001
                    err = resp.text[:300]
                fallback.error = f"http_{resp.status_code}: {err}"
                logger.error(
                    "[llm] explain FAIL tender_id=%s http=%s ms=%s error=%s",
                    tender_id,
                    resp.status_code,
                    elapsed_ms,
                    err,
                )
                return fallback
            data = resp.json()
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if not text:
                msg = (data.get("choices") or [{}])[0].get("message") or {}
                text = str(msg.get("reasoning_content") or msg.get("refusal") or "").strip()
            if not text:
                fallback.error = "empty_llm_content"
                logger.error(
                    "[llm] explain FAIL tender_id=%s reason=empty_content http=%s ms=%s",
                    tender_id,
                    resp.status_code,
                    elapsed_ms,
                )
                return fallback
            used_model = str(data.get("model") or cfg["model"])
            logger.info(
                "[llm] explain OK tender_id=%s source=llm_api model=%s ms=%s chars=%s hash=%s preview=%r",
                tender_id,
                used_model,
                elapsed_ms,
                len(text),
                ehash,
                text[:120],
            )
            return ExplainResult(
                text=text,
                provider=provider,
                model=used_model,
                prompt_version=PROMPT_VERSION,
                source="llm_api",
                evidence_hash=ehash,
                evidence=evidence,
                doc_extracts_to_persist=doc_extracts_to_persist
                if isinstance(doc_extracts_to_persist, list)
                else None,
            )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        err_label = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        fallback.error = f"llm_request_failed: {err_label}"
        logger.exception(
            "[llm] explain FAIL tender_id=%s ms=%s exception=%s",
            tender_id,
            elapsed_ms,
            err_label,
        )
        return fallback
