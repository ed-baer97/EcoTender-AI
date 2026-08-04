"""Verify risk explanation comes from LLM API (explanation_meta.source == llm_api)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = os.getenv("VITE_API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
REF = os.getenv("DEMO_TENDER_REF", "KZ-ECO-1001")


def main() -> int:
    url = f"{API}/tenders/{REF}/risk"
    req = urllib.request.Request(url, method="POST", data=b"")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"FAIL: cannot reach {url}: {exc}")
        return 2

    risk = data.get("risk") or data
    meta = risk.get("explanation_meta") or {}
    source = meta.get("source")
    print(f"tender={REF}")
    print(f"risk_score={risk.get('risk_score')} band={risk.get('risk_band')}")
    print(f"model_version={risk.get('model_version')}")
    print(f"explanation_meta={json.dumps(meta, ensure_ascii=False)}")
    text = (risk.get("explanation") or "")[:160]
    print(f"explanation_preview={text}")

    if source == "llm_api":
        print("OK: explanation_meta.source == llm_api")
        return 0

    print("FAIL: expected explanation_meta.source == llm_api")
    print("Hint: set LLM_API_KEY in .env and restart risk-engine:")
    print("  docker compose up -d --force-recreate risk-engine")
    return 1


if __name__ == "__main__":
    sys.exit(main())
