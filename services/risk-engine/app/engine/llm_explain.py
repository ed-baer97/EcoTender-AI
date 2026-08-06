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
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.engine.scoring import ScoreResult, template_explain

PROMPT_VERSION = "explain-v4-structured"
logger = logging.getLogger("ecotender.llm")

BAND_MIDPOINT = {"low": 18.0, "medium": 42.0, "high": 68.0, "critical": 86.0}


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
3) Слой модели (risk_score, reasons, anomalies) — индикатор. Если модель и документы расходятся (например, «завышение ×N», а в документах экономия) — conflict=true.
4) Если market_ignored_reason в key_features — не опирайся на «завышение цены» модели.
5) Не обвиняй в преступлениях; формулируй как аналитический риск.

Ответ — ТОЛЬКО один JSON-объект (без markdown-оградки), схема:
{
  "conflict": false,
  "agree_with_model": true,
  "auditor_band": "low|medium|high|critical",
  "auditor_summary": "одна фраза вердикта аудитора",
  "sections": {
    "verdict": "2–3 предложения",
    "evidence": ["факт 1", "факт 2", "факт 3"],
    "gaps": ["пробел 1", "пробел 2"],
    "recommendation": "мониторинг | углублённый аудит | приоритетный аудит"
  }
}"""


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
    sections: dict[str, Any] = field(default_factory=dict)
    conflict: bool = False
    agree_with_model: bool | None = None
    auditor_band: str | None = None
    auditor_summary: str | None = None


def format_explain_text(sections: dict[str, Any], *, auditor_summary: str | None = None) -> str:
    """Human-readable multi-line text for UI / cache."""
    parts: list[str] = []
    verdict = str(sections.get("verdict") or auditor_summary or "").strip()
    if verdict:
        parts.append(f"A) Вердикт\n{verdict}")
    evidence = sections.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    if evidence:
        bullets = "\n".join(f"• {str(x).strip()}" for x in evidence if str(x).strip())
        if bullets:
            parts.append(f"B) Подтверждения из документов\n{bullets}")
    gaps = sections.get("gaps") or []
    if isinstance(gaps, str):
        gaps = [gaps]
    if gaps:
        bullets = "\n".join(f"• {str(x).strip()}" for x in gaps if str(x).strip())
        if bullets:
            parts.append(f"C) Пробелы данных\n{bullets}")
    rec = str(sections.get("recommendation") or "").strip()
    if rec:
        parts.append(f"D) Рекомендация\n{rec}")
    return "\n\n".join(parts) if parts else (auditor_summary or "")


def parse_sections_from_plain_text(text: str) -> dict[str, Any]:
    """Best-effort split of legacy A)/B)/C)/D) walls of text."""
    if not text:
        return {}
    # Split on A) B) C) D) markers even when they are inline.
    chunks = re.split(r"(?=(?:^|\s)[ABCD]\))", text.strip())
    found: dict[str, str] = {}
    for chunk in chunks:
        m = re.match(r"\s*([ABCD])\)\s*(.*)", chunk, re.S)
        if m:
            found[m.group(1)] = m.group(2).strip()
    if not found:
        return {"verdict": text.strip()}

    def _bullets(block: str) -> list[str]:
        block = block.strip()
        if not block:
            return []
        if re.search(r"(?:^|\n)\s*[-•\d]", block):
            return [re.sub(r"^[-•\d\.\)\s]+", "", ln).strip() for ln in block.splitlines() if ln.strip()]
        parts = re.split(r"(?:(?<=\.)\s+|; )", block)
        return [p.strip() for p in parts if p.strip()][:6]

    sections: dict[str, Any] = {}
    if found.get("A"):
        # Strip leading label like "Вердикт:" if present
        a = re.sub(r"^(?:Вердикт|Verdict)\s*:\s*", "", found["A"], flags=re.I).strip()
        sections["verdict"] = a
    if found.get("B"):
        b = re.sub(r"^(?:Подтверждения[^\n:]*|Evidence)\s*:\s*", "", found["B"], flags=re.I).strip()
        sections["evidence"] = _bullets(b) or [b]
    if found.get("C"):
        c = re.sub(r"^(?:Пробелы[^\n:]*|Gaps)\s*:\s*", "", found["C"], flags=re.I).strip()
        sections["gaps"] = _bullets(c) or [c]
    if found.get("D"):
        d = re.sub(r"^(?:Рекомендация|Recommendation)\s*:\s*", "", found["D"], flags=re.I).strip()
        sections["recommendation"] = d
    return sections


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _normalize_band(value: Any) -> str | None:
    if value is None:
        return None
    b = str(value).strip().lower()
    if b in BAND_MIDPOINT:
        return b
    return None


def parse_llm_payload(raw_text: str, result: ScoreResult) -> ExplainResult:
    """Parse structured JSON or fall back to plain text sections."""
    data = _extract_json_object(raw_text)
    if data and isinstance(data.get("sections"), dict):
        sections_raw = data["sections"]
        evidence = sections_raw.get("evidence") or []
        gaps = sections_raw.get("gaps") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        if isinstance(gaps, str):
            gaps = [gaps]
        sections = {
            "verdict": str(sections_raw.get("verdict") or data.get("auditor_summary") or "").strip(),
            "evidence": [str(x).strip() for x in evidence if str(x).strip()],
            "gaps": [str(x).strip() for x in gaps if str(x).strip()],
            "recommendation": str(sections_raw.get("recommendation") or "").strip(),
        }
        conflict = bool(data.get("conflict"))
        agree = data.get("agree_with_model")
        if agree is not None:
            agree = bool(agree)
        auditor_band = _normalize_band(data.get("auditor_band")) or result.risk_band
        auditor_summary = str(data.get("auditor_summary") or sections.get("verdict") or "").strip()
        text = format_explain_text(sections, auditor_summary=auditor_summary)
        return ExplainResult(
            text=text,
            provider="",
            model="",
            prompt_version=PROMPT_VERSION,
            source="llm_api",
            sections=sections,
            conflict=conflict,
            agree_with_model=agree if agree is not None else (not conflict),
            auditor_band=auditor_band,
            auditor_summary=auditor_summary or None,
        )

    sections = parse_sections_from_plain_text(raw_text)
    text = format_explain_text(sections) if sections else raw_text.strip()
    low = (raw_text or "").lower()
    conflict = any(
        x in low for x in ("опроверг", "расхожд", "однако документ", "модель указывает")
    ) and any(x in low for x in ("экономи", "опроверг", "не переплат", "расхожд"))
    return ExplainResult(
        text=text or raw_text.strip(),
        provider="",
        model="",
        prompt_version=PROMPT_VERSION,
        source="llm_api",
        sections=sections,
        conflict=conflict,
        agree_with_model=not conflict,
        auditor_band=result.risk_band if not conflict else None,
        auditor_summary=(sections.get("verdict") if sections else None),
    )


def blend_scores_on_conflict(
    model_score: float,
    model_band: str,
    *,
    conflict: bool,
    auditor_band: str | None,
    overprice_driven: bool,
) -> dict[str, Any]:
    """When auditor contradicts model (esp. bad overprice), dampen display score."""
    if not conflict or not auditor_band:
        return {
            "risk_score": model_score,
            "risk_band": model_band,
            "model_risk_score": model_score,
            "model_risk_band": model_band,
            "confidence": "high",
            "conflict": False,
        }
    auditor_mid = BAND_MIDPOINT.get(auditor_band, model_score)
    weight_auditor = 0.7 if overprice_driven else 0.55
    blended = round((1.0 - weight_auditor) * model_score + weight_auditor * auditor_mid, 1)
    blended = min(blended, model_score)
    from ecotender_shared.enums import score_to_band

    return {
        "risk_score": blended,
        "risk_band": score_to_band(blended).value,
        "model_risk_score": model_score,
        "model_risk_band": model_band,
        "auditor_band": auditor_band,
        "confidence": "low",
        "conflict": True,
    }


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

    # Prefer features that explain market gating to the auditor model.
    prefer_keys = {
        "amount",
        "overprice_ratio",
        "overprice_ratio_raw",
        "market_match_confidence",
        "market_ignored_reason",
        "has_market_est",
        "participants_count",
        "single_bidder",
        "eco_category",
        "procurement_method",
        "region_code",
        "lots_count",
        "documents_count",
    }
    key_features = []
    for k, v in result.feature_vector.items():
        if k not in prefer_keys:
            continue
        if isinstance(v, str) or v is not None:
            key_features.append({"name": k, "value": v})
    for k, v in list(result.feature_vector.items())[:12]:
        if any(x["name"] == k for x in key_features):
            continue
        if not isinstance(v, str) or k in {"eco_category", "procurement_method", "region_code", "country_code"}:
            key_features.append({"name": k, "value": v})

    model_layer = {
        "risk_score": result.risk_score,
        "risk_band": result.risk_band,
        "model_version": result.model_version,
        "reasons": result.top_reasons,
        "anomalies": [
            {"anomaly_type": a.anomaly_type, "severity": a.severity, "evidence": a.evidence}
            for a in result.anomalies
        ],
        "key_features": key_features[:16],
        "market_estimate": extras.get("market_estimate") if isinstance(extras.get("market_estimate"), dict) else None,
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
    sections = cache.get("sections") if isinstance(cache.get("sections"), dict) else parse_sections_from_plain_text(text)
    if sections and not cache.get("sections"):
        text = format_explain_text(sections) or text
    return ExplainResult(
        text=text,
        provider=str(cache.get("provider") or "cache"),
        model=str(cache.get("model") or "cache"),
        prompt_version=str(cache.get("prompt_version") or PROMPT_VERSION),
        source="cache",
        evidence_hash=evidence_hash,
        sections=sections or {},
        conflict=bool(cache.get("conflict")),
        agree_with_model=cache.get("agree_with_model"),
        auditor_band=_normalize_band(cache.get("auditor_band")),
        auditor_summary=str(cache.get("auditor_summary") or "").strip() or None,
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

    template_sections = {
        "verdict": template_explain(result, title),
        "evidence": [r.get("message_ru") for r in result.top_reasons[:3] if r.get("message_ru")],
        "gaps": evidence.get("gaps") or [],
        "recommendation": (
            "приоритетный аудит"
            if result.risk_score >= 60
            else ("углублённый аудит" if result.risk_score >= 30 else "мониторинг")
        ),
    }
    fallback = ExplainResult(
        text=format_explain_text(template_sections),
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        source="template_fallback",
        evidence_hash=ehash,
        evidence=evidence,
        doc_extracts_to_persist=doc_extracts_to_persist if isinstance(doc_extracts_to_persist, list) else None,
        sections=template_sections,
        conflict=False,
        agree_with_model=True,
        auditor_band=result.risk_band,
        auditor_summary=template_sections["verdict"][:200],
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
        "max_tokens": 700,
        "enable_thinking": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Сформируй JSON-разбор по Evidence Pack:\n" + json.dumps(evidence, ensure_ascii=False),
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
            parsed = parse_llm_payload(text, result)
            parsed.provider = provider
            parsed.model = used_model
            parsed.prompt_version = PROMPT_VERSION
            parsed.source = "llm_api"
            parsed.evidence_hash = ehash
            parsed.evidence = evidence
            parsed.doc_extracts_to_persist = (
                doc_extracts_to_persist if isinstance(doc_extracts_to_persist, list) else None
            )
            logger.info(
                "[llm] explain OK tender_id=%s source=llm_api model=%s ms=%s chars=%s conflict=%s hash=%s preview=%r",
                tender_id,
                used_model,
                elapsed_ms,
                len(parsed.text),
                parsed.conflict,
                ehash,
                parsed.text[:120],
            )
            return parsed
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
