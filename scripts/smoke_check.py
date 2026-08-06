"""Smoke checklist before demo: health, ready, login, me, risk, goszakup artifacts."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = os.getenv("VITE_API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
GATEWAY = API.replace("/api/v1", "") if API.endswith("/api/v1") else "http://localhost:8000"
EMAIL = os.getenv("SMOKE_EMAIL", "admin@ecotender.kz")
PASSWORD = os.getenv("SMOKE_PASSWORD", "admin123")
TENDER_REF = os.getenv("DEMO_TENDER_REF", "KZ-ECO-1001")


def _request(method: str, url: str, *, data: dict | None = None, token: str | None = None) -> tuple[int, dict | list | str]:
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            try:
                parsed: dict | list | str = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed
    except urllib.error.URLError as exc:
        raise RuntimeError(f"cannot reach {url}: {exc}") from exc


def step(name: str, ok: bool, detail: str = "") -> bool:
    mark = "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{mark}] {name}{suffix}")
    return ok


def main() -> int:
    failed = 0
    print(f"smoke -> gateway={GATEWAY} api={API}")

    try:
        code, data = _request("GET", f"{GATEWAY}/health")
        ok = code == 200 and isinstance(data, dict) and data.get("status") == "ok"
        if not step("1. Gateway health", ok, f"HTTP {code}"):
            failed += 1
    except RuntimeError as exc:
        step("1. Gateway health", False, str(exc))
        return 1

    try:
        code, data = _request("GET", f"{API}/ready")
        services = (data or {}).get("services") if isinstance(data, dict) else {}
        down = [n for n, s in (services or {}).items() if not isinstance(s, dict) or s.get("status") != "ok"]
        ok = code == 200 and isinstance(data, dict) and data.get("ready") is True and not down
        detail = f"ready={isinstance(data, dict) and data.get('ready')}" + (f" down={','.join(down)}" if down else "")
        if not step("2. Ready / services", ok, detail):
            failed += 1
    except RuntimeError as exc:
        step("2. Ready / services", False, str(exc))
        failed += 1

    token = ""
    try:
        code, data = _request(
            "POST",
            f"{API}/auth/login",
            data={"email": EMAIL, "password": PASSWORD},
        )
        token = (data or {}).get("access_token", "") if isinstance(data, dict) else ""
        role = ((data or {}).get("user") or {}).get("role") if isinstance(data, dict) else None
        ok = code == 200 and bool(token)
        if not step("3. Login", ok, f"HTTP {code} role={role}"):
            failed += 1
            token = ""
    except RuntimeError as exc:
        step("3. Login", False, str(exc))
        failed += 1

    try:
        if not token:
            step("4. Auth me", False, "skipped (no token)")
            failed += 1
        else:
            code, data = _request("GET", f"{API}/auth/me", token=token)
            email = data.get("email") if isinstance(data, dict) else None
            ok = code == 200 and email == EMAIL
            if not step("4. Auth me", ok, f"HTTP {code} email={email}"):
                failed += 1
    except RuntimeError as exc:
        step("4. Auth me", False, str(exc))
        failed += 1

    try:
        code, data = _request("POST", f"{API}/tenders/{TENDER_REF}/risk")
        risk = (data or {}).get("risk") if isinstance(data, dict) else None
        if not isinstance(risk, dict):
            risk = data if isinstance(data, dict) else {}
        score = risk.get("risk_score") if isinstance(risk, dict) else None
        ok = code == 200 and score is not None
        if not step("5. Risk score", ok, f"HTTP {code} score={score} band={risk.get('risk_band') if isinstance(risk, dict) else None}"):
            failed += 1
    except RuntimeError as exc:
        step("5. Risk score", False, str(exc))
        failed += 1

    try:
        code, data = _request("GET", f"{API}/tenders/{TENDER_REF}/artifacts", token=token or None)
        docs = len((data or {}).get("documents") or []) if isinstance(data, dict) else 0
        tabs = len((data or {}).get("tabs") or []) if isinstance(data, dict) else 0
        ok = code == 200 and isinstance(data, dict)
        if not step("6. Goszakup artifacts", ok, f"HTTP {code} docs={docs} tabs={tabs}"):
            failed += 1
    except RuntimeError as exc:
        step("6. Goszakup artifacts", False, str(exc))
        failed += 1

    if failed:
        print(f"SMOKE FAILED ({failed} step(s))")
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
