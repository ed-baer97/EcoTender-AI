"""API Gateway / BFF — auth, request-id, reverse proxy to domain services."""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="EcoTender API Gateway", version="0.1.0")

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
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")

# Demo users for hackathon (replace with IAM later)
DEMO_USERS = {
    "analyst@ecotender.kz": {"password": "analyst123", "role": "analyst", "name": "Аналитик"},
    "admin@ecotender.kz": {"password": "admin123", "role": "admin", "name": "Администратор"},
    "viewer@ecotender.kz": {"password": "viewer123", "role": "viewer", "name": "Наблюдатель"},
}


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _issue_jwt(email: str, role: str, name: str) -> str:
    import hashlib
    import hmac
    import json
    import time

    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps(
            {
                "sub": email,
                "role": role,
                "name": name,
                "exp": int(time.time()) + 60 * 60 * 12,
            }
        ).encode()
    )
    sig = hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def _decode_jwt(token: str) -> dict[str, Any] | None:
    import hashlib
    import hmac
    import json
    import time
    import base64

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
    auth = request.headers.get("Authorization") or ""
    token = auth.replace("Bearer ", "").strip()
    data = _decode_jwt(token) if token else None
    if not data:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"email": data.get("sub"), "role": data.get("role"), "name": data.get("name")}


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
    return {
        "sources": [
            {
                "code": "KZ_GOSZAKUP_OWS_V3",
                "country_code": "KZ",
                "name": "goszakup.gov.kz OWS v3",
                "docs": "https://goszakup.gov.kz/ru/developer/ows_v3",
                "auth": "Bearer token via GOSZAKUP_TOKEN (offline sample if empty)",
            },
            {
                "code": "FIXTURES_CASPIAN",
                "country_code": "KZ",
                "name": "Local JSON fixtures",
                "docs": None,
                "auth": None,
            },
        ]
    }


@app.post("/api/v1/ingest/sources/{source_code}/run")
async def ingest_run(source_code: str) -> dict[str, Any]:
    """Enqueue Celery crawl_source task."""
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


@app.post("/api/v1/tenders/{tender_ref}/risk")
async def score_tender_card(tender_ref: str) -> Any:
    """Compose tender + risk for UI convenience (BFF pattern)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        t = await client.get(f"{SERVICES['tender']}/v1/tenders/{tender_ref}")
        tender = t.json()
        payload = {
            "tender_id": tender.get("id"),
            "title": tender.get("title"),
            "features": tender,
        }
        r = await client.post(f"{SERVICES['risk']}/v1/score", json=payload)
        risk = r.json()
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
