"""API Gateway / BFF — auth, admin secrets, reverse proxy to domain services."""

from __future__ import annotations

import logging
import os
import time
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ecotender_shared.runtime_secrets import (
    ALLOWED_KEYS,
    activate_llm,
    activate_parser,
    bootstrap_from_file,
    create_llm,
    create_parser,
    delete_config_value,
    delete_llm,
    delete_parser,
    get_active_llm_raw,
    get_config_value,
    get_integrations,
    list_audit,
    list_config,
    set_config_value,
    update_llm,
    update_parser,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("ecotender.gateway")

app = FastAPI(title="EcoTender API Gateway", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVICES = {
    "tender": os.getenv("TENDER_SERVICE_URL", "http://localhost:8001"),
    "market": os.getenv("MARKET_SERVICE_URL", "http://localhost:8002"),
    "geo": os.getenv("GEO_SERVICE_URL", "http://localhost:8003"),
    "risk": os.getenv("RISK_SERVICE_URL", "http://localhost:8004"),
}
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/1"))
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")

DEMO_USERS = {
    "analyst@ecotender.kz": {"password": "analyst123", "role": "analyst", "name": "Аналитик"},
    "admin@ecotender.kz": {"password": "admin123", "role": "admin", "name": "Администратор"},
    "viewer@ecotender.kz": {"password": "viewer123", "role": "viewer", "name": "Наблюдатель"},
}


@app.on_event("startup")
def _startup() -> None:
    bootstrap_from_file()


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _issue_jwt(email: str, role: str, name: str) -> str:
    import hashlib
    import hmac
    import json
    import time

    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(
        json.dumps(
            {
                "sub": email,
                "role": role,
                "name": name,
                "exp": int(time.time()) + 60 * 60 * 12,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    )
    sig = hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def _decode_jwt(token: str) -> dict[str, Any] | None:
    import base64
    import hashlib
    import hmac
    import json
    import time

    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        expected = _b64url(
            hmac.new(JWT_SECRET.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(expected, sig_b64):
            return None
        pad = "=" * (-len(payload_b64) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload_b64 + pad))
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


def _require_user(request: Request) -> dict[str, Any]:
    auth = request.headers.get("Authorization") or ""
    token = auth.replace("Bearer ", "").strip()
    data = _decode_jwt(token) if token else None
    if not data:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return data


def _require_admin(request: Request) -> dict[str, Any]:
    data = _require_user(request)
    if data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return data


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id", str(uuid4()))
    response: Response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "api-gateway"}


class LoginBody(BaseModel):
    email: str
    password: str = Field(min_length=1)


class SecretUpsert(BaseModel):
    value: str = Field(min_length=1, max_length=4000)


class LlmBody(BaseModel):
    name: str | None = None
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    active: bool | None = None


class ParserBody(BaseModel):
    name: str | None = None
    source_code: str | None = None
    token: str | None = None
    base_url: str | None = None
    country_code: str | None = None
    active: bool | None = None


@app.post("/api/v1/auth/login")
async def login(body: LoginBody) -> dict[str, Any]:
    email = body.email.strip().lower()
    user = DEMO_USERS.get(email)
    if not user or user["password"] != body.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _issue_jwt(email, user["role"], user["name"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"email": email, "role": user["role"], "name": user["name"]},
    }


@app.get("/api/v1/auth/me")
async def me(request: Request) -> dict[str, Any]:
    data = _require_user(request)
    return {"email": data.get("sub"), "role": data.get("role"), "name": data.get("name")}


# ── Integrations (LLM + parsers) ─────────────────────────────────────────────


@app.get("/api/v1/admin/integrations")
async def admin_integrations(request: Request) -> dict[str, Any]:
    _require_admin(request)
    data = get_integrations(mask=True)
    return {
        **data,
        "llm_count": len(data["llms"]),
        "parser_count": len(data["parsers"]),
    }


@app.post("/api/v1/admin/integrations/llms")
async def admin_create_llm(body: LlmBody, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    if not body.name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        data = create_llm(body.model_dump(exclude_none=True), actor=str(admin.get("sub") or "admin"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **data}


@app.put("/api/v1/admin/integrations/llms/{llm_id}")
async def admin_update_llm(llm_id: str, body: LlmBody, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    try:
        data = update_llm(llm_id, body.model_dump(exclude_none=True), actor=str(admin.get("sub") or "admin"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"LLM not found: {llm_id}") from exc
    return {"ok": True, **data}


@app.delete("/api/v1/admin/integrations/llms/{llm_id}")
async def admin_delete_llm(llm_id: str, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    try:
        data = delete_llm(llm_id, actor=str(admin.get("sub") or "admin"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **data}


@app.post("/api/v1/admin/integrations/llms/{llm_id}/activate")
async def admin_activate_llm(llm_id: str, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    try:
        data = activate_llm(llm_id, actor=str(admin.get("sub") or "admin"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, **data}


@app.post("/api/v1/admin/integrations/llms/{llm_id}/test")
async def admin_test_llm_by_id(llm_id: str, request: Request) -> dict[str, Any]:
    _require_admin(request)
    from ecotender_shared.runtime_secrets import INTEGRATIONS_KEY, _ensure_integrations, _read_raw_store

    raw = _ensure_integrations(_read_raw_store())
    llm = next((x for x in raw[INTEGRATIONS_KEY]["llms"] if x["id"] == llm_id), None)
    if not llm:
        raise HTTPException(status_code=404, detail="LLM not found")
    api_key = llm.get("api_key") or ""
    base_url = (llm.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = llm.get("model") or "gpt-5.6-terra"
    if not api_key:
        raise HTTPException(status_code=400, detail="API key пуст — сначала сохраните ключ")
    return await _ping_llm(api_key=api_key, base_url=base_url, model=model)


@app.post("/api/v1/admin/integrations/parsers")
async def admin_create_parser(body: ParserBody, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    if not body.name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        data = create_parser(body.model_dump(exclude_none=True), actor=str(admin.get("sub") or "admin"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **data}


@app.put("/api/v1/admin/integrations/parsers/{parser_id}")
async def admin_update_parser(parser_id: str, body: ParserBody, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    try:
        data = update_parser(parser_id, body.model_dump(exclude_none=True), actor=str(admin.get("sub") or "admin"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Parser not found: {parser_id}") from exc
    return {"ok": True, **data}


@app.delete("/api/v1/admin/integrations/parsers/{parser_id}")
async def admin_delete_parser(parser_id: str, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    try:
        data = delete_parser(parser_id, actor=str(admin.get("sub") or "admin"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **data}


@app.post("/api/v1/admin/integrations/parsers/{parser_id}/activate")
async def admin_activate_parser(parser_id: str, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    try:
        data = activate_parser(parser_id, actor=str(admin.get("sub") or "admin"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, **data}


def _mask_key(api_key: str | None) -> str:
    if not api_key:
        return "(empty)"
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:3]}…{api_key[-4:]}"


async def _ping_llm(*, api_key: str, base_url: str, model: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "Reply with OK"}],
    }
    logger.info(
        "[llm-test] start model=%s base=%s key=%s",
        model,
        base_url,
        _mask_key(api_key),
    )
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            ok = resp.status_code < 400
            body: dict[str, Any] = {}
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = {"raw": resp.text[:300]}
            preview = (
                (body.get("choices") or [{}])[0].get("message", {}).get("content")
                if ok
                else body.get("error") or body
            )
            if ok:
                logger.info(
                    "[llm-test] OK http=%s ms=%s model=%s preview=%r",
                    resp.status_code,
                    elapsed_ms,
                    model,
                    preview,
                )
            else:
                logger.error(
                    "[llm-test] FAIL http=%s ms=%s model=%s error=%s",
                    resp.status_code,
                    elapsed_ms,
                    model,
                    preview,
                )
            return {
                "ok": ok,
                "status_code": resp.status_code,
                "model": model,
                "base_url": base_url,
                "preview": preview,
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception("[llm-test] FAIL exception=%s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/v1/admin/secrets")
async def admin_list_secrets(request: Request) -> dict[str, Any]:
    _require_admin(request)
    items = list_config()
    return {"items": items, "total": len(items)}


@app.put("/api/v1/admin/secrets/{key}")
async def admin_set_secret(key: str, body: SecretUpsert, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown key: {key}")
    item = set_config_value(key, body.value, actor=str(admin.get("sub") or "admin"))
    return {"ok": True, "item": item}


@app.delete("/api/v1/admin/secrets/{key}")
async def admin_delete_secret(key: str, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown key: {key}")
    item = delete_config_value(key, actor=str(admin.get("sub") or "admin"))
    return {"ok": True, "item": item}


@app.get("/api/v1/admin/audit")
async def admin_secrets_audit(request: Request, limit: int = 50) -> dict[str, Any]:
    _require_admin(request)
    return {"items": list_audit(limit=min(limit, 200))}


@app.post("/api/v1/admin/secrets/LLM_API_KEY/test")
async def admin_test_llm(request: Request) -> dict[str, Any]:
    _require_admin(request)
    llm = get_active_llm_raw()
    api_key = (llm or {}).get("api_key") or get_config_value("LLM_API_KEY")
    base_url = ((llm or {}).get("base_url") or get_config_value("LLM_BASE_URL", "https://api.openai.com/v1") or "").rstrip(
        "/"
    )
    model = (llm or {}).get("model") or get_config_value("LLM_MODEL", "gpt-5.6-terra") or "gpt-5.6-terra"
    if not api_key:
        raise HTTPException(status_code=400, detail="LLM_API_KEY is empty — save a key first")
    return await _ping_llm(api_key=api_key, base_url=base_url, model=model)

@app.get("/api/v1/admin/overview")
async def admin_overview(request: Request) -> dict[str, Any]:
    _require_admin(request)
    integ = get_integrations(mask=True)
    statuses: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, base in SERVICES.items():
            try:
                r = await client.get(f"{base}/health")
                statuses[name] = r.json()
            except Exception as exc:  # noqa: BLE001
                statuses[name] = {"status": "down", "error": str(exc)}
    return {
        "services": statuses,
        "llm_count": len(integ["llms"]),
        "parser_count": len(integ["parsers"]),
        "keys_configured": sum(1 for s in list_config() if s.get("configured")),
        "keys_total": len(list_config()),
        "llm_ready": any(x.get("api_key_set") for x in integ["llms"]),
        "goszakup_ready": any(x.get("token_set") for x in integ["parsers"]),
    }


@app.get("/api/v1/ready")
async def ready() -> dict[str, Any]:
    statuses = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, base in SERVICES.items():
            try:
                r = await client.get(f"{base}/health")
                statuses[name] = r.json()
            except Exception as exc:  # noqa: BLE001
                statuses[name] = {"status": "down", "error": str(exc)}
    ok = all(v.get("status") == "ok" for v in statuses.values())
    return {"ready": ok, "services": statuses}


@app.get("/api/v1/ingest/sources")
async def ingest_sources() -> dict[str, Any]:
    integ = get_integrations(mask=True)
    sources = []
    for p in integ.get("parsers") or []:
        sources.append(
            {
                "code": p.get("source_code"),
                "id": p.get("id"),
                "name": p.get("name"),
                "country_code": p.get("country_code"),
                "active": p.get("active"),
                "token_set": p.get("token_set"),
                "auth": "Bearer token via admin integrations",
            }
        )
    if not any(s.get("code") == "FIXTURES_CASPIAN" for s in sources):
        sources.append(
            {
                "code": "FIXTURES_CASPIAN",
                "country_code": "KZ",
                "name": "Local JSON fixtures",
                "docs": None,
                "auth": None,
            }
        )
    if not any(s.get("code") == "KZ_GOSZAKUP_PLAYWRIGHT" for s in sources):
        sources.append(
            {
                "code": "KZ_GOSZAKUP_PLAYWRIGHT",
                "country_code": "KZ",
                "name": "goszakup portal (Playwright stub)",
                "docs": "https://goszakup.gov.kz/ru/search/announce",
                "auth": "Public HTML — no OWS token",
            }
        )
    return {"sources": sources}


@app.delete("/api/v1/admin/tenders/synthetic")
async def purge_synthetic_tenders(request: Request) -> dict[str, Any]:
    _require_admin(request)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(f"{SERVICES['tender']}/v1/tenders/by-source/synthetic")
        resp.raise_for_status()
        return resp.json()


@app.post("/api/v1/ingest/sources/{source_code}/run")
async def ingest_run(source_code: str, request: Request) -> dict[str, Any]:
    user = _require_user(request)
    if user.get("role") not in {"admin", "analyst"}:
        raise HTTPException(status_code=403, detail="analyst or admin required")
    try:
        from celery import Celery

        capp = Celery(broker=CELERY_BROKER_URL)
        async_result = capp.send_task(
            "app.workers.tasks.crawl_source",
            args=[source_code],
            queue="ingest",
        )
        return {
            "status": "queued",
            "source_code": source_code,
            "task_id": async_result.id,
            "flower": "http://localhost:5555",
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": str(exc)}


@app.get("/api/v1/ingest/tasks/{task_id}")
async def ingest_task_status(task_id: str, request: Request) -> dict[str, Any]:
    _require_user(request)
    from celery import Celery

    capp = Celery(broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)
    result = capp.AsyncResult(task_id)
    meta = result.info if isinstance(result.info, dict) else {}
    payload: dict[str, Any] = {
        "task_id": task_id,
        "state": result.state,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else False,
        "meta": meta,
    }
    if result.ready():
        payload["result"] = result.result
    return payload


async def _proxy(base: str, path: str, request: Request) -> Response:
    url = f"{base}{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        body = await request.body()
        upstream = await client.request(
            request.method,
            url,
            content=body,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
        )
    return Response(content=upstream.content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type"))


def _risk_from_saved_cache(tender: dict[str, Any], cached: dict[str, Any]) -> dict[str, Any]:
    """Rebuild risk payload from persisted llm_explain — no CatBoost/LLM."""
    score = cached.get("risk_score") if cached.get("risk_score") is not None else tender.get("risk_score")
    band = cached.get("risk_band") or tender.get("risk_band")
    meta = {
        "provider": cached.get("provider"),
        "model": cached.get("model"),
        "prompt_version": cached.get("prompt_version"),
        "source": "cache",
        "evidence_hash": cached.get("evidence_hash"),
        "confidence": cached.get("confidence"),
        "conflict": cached.get("conflict"),
    }
    if cached.get("error"):
        meta["error"] = cached["error"]
    return {
        "tender_id": tender.get("id"),
        "risk_score": score,
        "risk_band": band,
        "model_risk_score": cached.get("model_risk_score", score),
        "model_risk_band": cached.get("model_risk_band", band),
        "model_version": None,
        "scored_at": cached.get("scored_at"),
        "explanation": cached.get("text"),
        "explanation_sections": cached.get("sections") or {},
        "explanation_meta": meta,
        "verdicts": cached.get("verdicts") or {},
        "evidence_summary": cached.get("evidence_summary"),
        "reasons": [],
        "anomalies": [],
        "feature_vector": {},
    }


@app.post("/api/v1/tenders/{tender_ref}/risk")
async def score_tender_card(tender_ref: str, force: bool = False) -> Any:
    async with httpx.AsyncClient(timeout=120.0) as client:
        t = await client.get(f"{SERVICES['tender']}/v1/tenders/{tender_ref}")
        tender = t.json()
        extras = tender.get("extras") if isinstance(tender.get("extras"), dict) else {}
        cached = extras.get("llm_explain") if isinstance(extras, dict) else None
        if (
            not force
            and not extras.get("risk_stale")
            and isinstance(cached, dict)
            and cached.get("text")
            and cached.get("risk_score") is not None
        ):
            logger.info("[risk] cache hit tender_ref=%s — skip rescore", tender_ref)
            return {"tender": tender, "risk": _risk_from_saved_cache(tender, cached)}

        payload = {
            "tender_id": tender.get("id"),
            "title": tender.get("title"),
            "features": tender,
            "force": force,
        }
        logger.info("[risk] score proxy start tender_ref=%s force=%s", tender_ref, force)
        r = await client.post(f"{SERVICES['risk']}/v1/score", json=payload)
        risk = r.json()
        meta = risk.get("explanation_meta") if isinstance(risk, dict) else None
        logger.info(
            "[risk] score proxy done tender_ref=%s http=%s source=%s hash=%s",
            tender_ref,
            r.status_code,
            (meta or {}).get("source") if isinstance(meta, dict) else None,
            (meta or {}).get("evidence_hash") if isinstance(meta, dict) else None,
        )
        # Persist score + LLM explain cache so reopen skips Qwen.
        if isinstance(risk, dict) and risk.get("risk_score") is not None:
            extras = dict(tender.get("extras") or {})
            gos = dict(extras.get("goszakup") or {}) if isinstance(extras.get("goszakup"), dict) else {}
            if isinstance(risk.get("doc_extracts"), list) and risk.get("doc_extracts"):
                gos["doc_extracts"] = risk["doc_extracts"]
                extras["goszakup"] = gos
            if isinstance(meta, dict) and risk.get("explanation"):
                extras["llm_explain"] = {
                    "text": risk.get("explanation"),
                    "sections": risk.get("explanation_sections") or {},
                    "verdicts": risk.get("verdicts") or {},
                    "provider": meta.get("provider"),
                    "model": meta.get("model"),
                    "prompt_version": meta.get("prompt_version"),
                    "source": meta.get("source"),
                    "evidence_hash": meta.get("evidence_hash"),
                    "scored_at": risk.get("scored_at"),
                    "risk_score": risk.get("risk_score"),
                    "risk_band": risk.get("risk_band"),
                    "model_risk_score": risk.get("model_risk_score"),
                    "model_risk_band": risk.get("model_risk_band"),
                    "conflict": (risk.get("verdicts") or {}).get("conflict") or meta.get("conflict"),
                    "confidence": (risk.get("verdicts") or {}).get("confidence") or meta.get("confidence"),
                    "auditor_band": ((risk.get("verdicts") or {}).get("auditor") or {}).get("risk_band"),
                    "auditor_summary": ((risk.get("verdicts") or {}).get("auditor") or {}).get("summary"),
                    "agree_with_model": ((risk.get("verdicts") or {}).get("auditor") or {}).get("agree_with_model"),
                    "evidence_summary": risk.get("evidence_summary"),
                    **({"error": meta["error"]} if meta.get("error") else {}),
                }
            extras.pop("risk_stale", None)
            upsert = {
                **{k: v for k, v in tender.items() if k not in ("id", "ingested_at")},
                "risk_score": risk.get("risk_score"),
                "risk_band": risk.get("risk_band"),
                "extras": extras,
            }
            try:
                up = await client.post(f"{SERVICES['tender']}/v1/tenders/upsert", json=upsert)
                if up.status_code < 400:
                    tender = up.json()
            except Exception:
                pass
    return {"tender": tender, "risk": risk}


@app.post("/api/v1/score")
async def score_proxy(request: Request) -> Response:
    return await _proxy(SERVICES["risk"], "/v1/score", request)


@app.api_route("/api/v1/contractors/{path:path}", methods=["GET"])
@app.api_route("/api/v1/contractors", methods=["GET"])
async def contractors_proxy(request: Request, path: str = "") -> Response:
    suffix = f"/v1/contractors/{path}" if path else "/v1/contractors"
    return await _proxy(SERVICES["tender"], suffix, request)


@app.api_route("/api/v1/tenders/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.api_route("/api/v1/tenders", methods=["GET", "POST"])
async def tenders_proxy(request: Request, path: str = "") -> Response:
    suffix = f"/v1/tenders/{path}" if path else "/v1/tenders"
    return await _proxy(SERVICES["tender"], suffix, request)


@app.api_route("/api/v1/market/{path:path}", methods=["GET", "POST"])
@app.api_route("/api/v1/market", methods=["GET", "POST"])
async def market_proxy(request: Request, path: str = "") -> Response:
    suffix = f"/v1/market/{path}" if path else "/v1/market/items"
    return await _proxy(SERVICES["market"], suffix, request)


@app.api_route("/api/v1/map/{path:path}", methods=["GET"])
async def map_proxy(request: Request, path: str) -> Response:
    return await _proxy(SERVICES["geo"], f"/v1/map/{path}", request)


@app.api_route("/api/v1/risk/{path:path}", methods=["GET", "POST"])
async def risk_proxy(request: Request, path: str) -> Response:
    return await _proxy(SERVICES["risk"], f"/v1/{path}", request)
