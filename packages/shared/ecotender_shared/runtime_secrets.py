"""Runtime integrations — LLM providers & parsing services.

Stored as JSON in Redis + file. Active LLM/parser sync to flat env-style keys
so existing consumers (llm_explain, goszakup) keep working via get_config_value().
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

REDIS_HASH = "ecotender:runtime_config"
REDIS_AUDIT = "ecotender:runtime_config:audit"
INTEGRATIONS_KEY = "integrations"
DEFAULT_FILE = Path(os.getenv("RUNTIME_CONFIG_PATH", "/data/runtime/config.json"))

DEFAULT_LLMS: list[dict[str, Any]] = [
    {
        "id": "openai-default",
        "name": "OpenAI (default)",
        "provider": "openai",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.6-terra",
        "active": True,
    }
]

DEFAULT_PARSERS: list[dict[str, Any]] = [
    {
        "id": "kz-goszakup",
        "name": "Goszakup KZ OWS v3",
        "source_code": "KZ_GOSZAKUP_OWS_V3",
        "token": "",
        "base_url": "https://ows.goszakup.gov.kz",
        "country_code": "KZ",
        "active": True,
    }
]

# Flat keys still writable for backward compatibility / get_config_value
FLAT_KEYS = {
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_PROVIDER",
    "GOSZAKUP_TOKEN",
    "GOSZAKUP_BASE_URL",
}
ALLOWED_KEYS = FLAT_KEYS  # legacy alias


def _redis():
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis

        return redis.from_url(url, decode_responses=True, socket_connect_timeout=1.5)
    except Exception:  # noqa: BLE001
        return None


def _load_file(path: Path = DEFAULT_FILE) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_file(values: dict[str, Any], path: Path = DEFAULT_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "-", name.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return (s or "item")[:40]


def _new_id(prefix: str, name: str) -> str:
    return f"{prefix}-{_slug(name)}-{uuid.uuid4().hex[:6]}"


def _audit(action: str, key: str, actor: str, masked: str | None = None) -> None:
    client = _redis()
    if not client:
        return
    try:
        client.lpush(
            REDIS_AUDIT,
            json.dumps(
                {"ts": int(time.time()), "action": action, "key": key, "actor": actor, "masked": masked},
                ensure_ascii=False,
            ),
        )
        client.ltrim(REDIS_AUDIT, 0, 199)
    except Exception:  # noqa: BLE001
        return


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:4]}…{value[-4:]}"


def _read_raw_store() -> dict[str, Any]:
    """Merge Redis hash + file into one dict (Redis wins for scalar keys)."""
    store = _load_file()
    client = _redis()
    if client:
        try:
            for k, v in (client.hgetall(REDIS_HASH) or {}).items():
                if k == INTEGRATIONS_KEY:
                    try:
                        store[INTEGRATIONS_KEY] = json.loads(v)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    store[k] = v
        except Exception:  # noqa: BLE001
            pass
    return store


def _write_store(store: dict[str, Any]) -> None:
    _save_file(store)
    client = _redis()
    if not client:
        return
    try:
        pipe = client.pipeline()
        for k, v in store.items():
            if k == INTEGRATIONS_KEY:
                pipe.hset(REDIS_HASH, k, json.dumps(v, ensure_ascii=False))
            elif v is None:
                pipe.hdel(REDIS_HASH, k)
            else:
                pipe.hset(REDIS_HASH, k, str(v))
        pipe.execute()
    except Exception:  # noqa: BLE001
        return


def _sync_flat_from_integrations(store: dict[str, Any]) -> None:
    """Push active LLM / parser fields into flat keys for consumers."""
    integ = store.get(INTEGRATIONS_KEY) or {}
    llms = integ.get("llms") or []
    parsers = integ.get("parsers") or []
    active_llm = next((x for x in llms if x.get("active")), llms[0] if llms else None)
    active_parser = next((x for x in parsers if x.get("active")), parsers[0] if parsers else None)

    if active_llm:
        if active_llm.get("api_key"):
            store["LLM_API_KEY"] = active_llm["api_key"]
        store["LLM_BASE_URL"] = active_llm.get("base_url") or "https://api.openai.com/v1"
        store["LLM_MODEL"] = active_llm.get("model") or "gpt-5.6-terra"
        store["LLM_PROVIDER"] = active_llm.get("provider") or "openai"
    if active_parser:
        if active_parser.get("token"):
            store["GOSZAKUP_TOKEN"] = active_parser["token"]
        if active_parser.get("base_url"):
            store["GOSZAKUP_BASE_URL"] = active_parser["base_url"]


def _ensure_integrations(store: dict[str, Any]) -> dict[str, Any]:
    integ = store.get(INTEGRATIONS_KEY)
    if not isinstance(integ, dict):
        integ = {}
    llms = list(integ.get("llms") or [])
    parsers = list(integ.get("parsers") or [])

    if not llms:
        seeded = {**DEFAULT_LLMS[0]}
        # migrate legacy flat key into seed
        flat_key = store.get("LLM_API_KEY") or os.getenv("LLM_API_KEY") or ""
        if flat_key:
            seeded["api_key"] = flat_key
        if store.get("LLM_BASE_URL") or os.getenv("LLM_BASE_URL"):
            seeded["base_url"] = store.get("LLM_BASE_URL") or os.getenv("LLM_BASE_URL")
        if store.get("LLM_MODEL") or os.getenv("LLM_MODEL"):
            seeded["model"] = store.get("LLM_MODEL") or os.getenv("LLM_MODEL")
        if store.get("LLM_PROVIDER") or os.getenv("LLM_PROVIDER"):
            seeded["provider"] = store.get("LLM_PROVIDER") or os.getenv("LLM_PROVIDER")
        llms = [seeded]

    if not parsers:
        seeded = {**DEFAULT_PARSERS[0]}
        flat_tok = store.get("GOSZAKUP_TOKEN") or os.getenv("GOSZAKUP_TOKEN") or ""
        if flat_tok:
            seeded["token"] = flat_tok
        if store.get("GOSZAKUP_BASE_URL") or os.getenv("GOSZAKUP_BASE_URL"):
            seeded["base_url"] = store.get("GOSZAKUP_BASE_URL") or os.getenv("GOSZAKUP_BASE_URL")
        parsers = [seeded]

    store[INTEGRATIONS_KEY] = {"llms": llms, "parsers": parsers}
    return store


def bootstrap_from_file() -> None:
    store = _ensure_integrations(_read_raw_store())
    _sync_flat_from_integrations(store)
    _write_store(store)


def get_config_value(key: str, default: str | None = None) -> str | None:
    store = _ensure_integrations(_read_raw_store())
    _sync_flat_from_integrations(store)
    val = store.get(key)
    if val is not None and str(val).strip() != "":
        return str(val)
    env = os.getenv(key)
    if env is not None and str(env).strip() != "":
        return env
    return default


def get_integrations(*, mask: bool = True) -> dict[str, Any]:
    store = _ensure_integrations(_read_raw_store())
    integ = store[INTEGRATIONS_KEY]
    llms = []
    for item in integ.get("llms") or []:
        row = {**item}
        if mask:
            row["api_key_masked"] = mask_secret(item.get("api_key"))
            row["api_key_set"] = bool(item.get("api_key"))
            row.pop("api_key", None)
        llms.append(row)
    parsers = []
    for item in integ.get("parsers") or []:
        row = {**item}
        if mask:
            row["token_masked"] = mask_secret(item.get("token"))
            row["token_set"] = bool(item.get("token"))
            row.pop("token", None)
        parsers.append(row)
    return {"llms": llms, "parsers": parsers}


def _save_integrations(llms: list[dict], parsers: list[dict], *, actor: str, action: str, key: str) -> dict[str, Any]:
    store = _ensure_integrations(_read_raw_store())
    store[INTEGRATIONS_KEY] = {"llms": llms, "parsers": parsers}
    _sync_flat_from_integrations(store)
    _write_store(store)
    _audit(action, key, actor)
    return get_integrations(mask=True)


# ── LLM CRUD ────────────────────────────────────────────────────────────────


def create_llm(body: dict[str, Any], *, actor: str = "admin") -> dict[str, Any]:
    store = _ensure_integrations(_read_raw_store())
    llms = list(store[INTEGRATIONS_KEY]["llms"])
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    item = {
        "id": body.get("id") or _new_id("llm", name),
        "name": name,
        "provider": (body.get("provider") or "openai").strip(),
        "api_key": (body.get("api_key") or "").strip(),
        "base_url": (body.get("base_url") or "https://api.openai.com/v1").strip().rstrip("/"),
        "model": (body.get("model") or "gpt-5.6-terra").strip(),
        "active": bool(body.get("active", False)),
    }
    if item["active"]:
        for x in llms:
            x["active"] = False
    elif not llms:
        item["active"] = True
    llms.append(item)
    return _save_integrations(llms, store[INTEGRATIONS_KEY]["parsers"], actor=actor, action="create_llm", key=item["id"])


def update_llm(llm_id: str, body: dict[str, Any], *, actor: str = "admin") -> dict[str, Any]:
    store = _ensure_integrations(_read_raw_store())
    llms = list(store[INTEGRATIONS_KEY]["llms"])
    idx = next((i for i, x in enumerate(llms) if x["id"] == llm_id), None)
    if idx is None:
        raise KeyError(llm_id)
    cur = {**llms[idx]}
    for field in ("name", "provider", "base_url", "model"):
        if field in body and body[field] is not None:
            cur[field] = str(body[field]).strip()
    if "api_key" in body and body["api_key"] is not None and str(body["api_key"]).strip() != "":
        cur["api_key"] = str(body["api_key"]).strip()
    if "active" in body:
        cur["active"] = bool(body["active"])
        if cur["active"]:
            for x in llms:
                x["active"] = False
    llms[idx] = cur
    return _save_integrations(llms, store[INTEGRATIONS_KEY]["parsers"], actor=actor, action="update_llm", key=llm_id)


def delete_llm(llm_id: str, *, actor: str = "admin") -> dict[str, Any]:
    store = _ensure_integrations(_read_raw_store())
    llms = [x for x in store[INTEGRATIONS_KEY]["llms"] if x["id"] != llm_id]
    if not llms:
        raise ValueError("Cannot delete the last LLM")
    if not any(x.get("active") for x in llms):
        llms[0]["active"] = True
    return _save_integrations(llms, store[INTEGRATIONS_KEY]["parsers"], actor=actor, action="delete_llm", key=llm_id)


def activate_llm(llm_id: str, *, actor: str = "admin") -> dict[str, Any]:
    return update_llm(llm_id, {"active": True}, actor=actor)


def get_active_llm_raw() -> dict[str, Any] | None:
    store = _ensure_integrations(_read_raw_store())
    llms = store[INTEGRATIONS_KEY]["llms"]
    return next((x for x in llms if x.get("active")), llms[0] if llms else None)


# ── Parser CRUD ──────────────────────────────────────────────────────────────


def create_parser(body: dict[str, Any], *, actor: str = "admin") -> dict[str, Any]:
    store = _ensure_integrations(_read_raw_store())
    parsers = list(store[INTEGRATIONS_KEY]["parsers"])
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    source_code = (body.get("source_code") or "").strip().upper().replace(" ", "_")
    if not source_code:
        source_code = f"CUSTOM_{_slug(name).upper().replace('-', '_')}"
    item = {
        "id": body.get("id") or _new_id("parser", name),
        "name": name,
        "source_code": source_code,
        "token": (body.get("token") or "").strip(),
        "base_url": (body.get("base_url") or "").strip().rstrip("/"),
        "country_code": (body.get("country_code") or "KZ").strip().upper()[:2],
        "active": bool(body.get("active", False)),
    }
    if item["active"]:
        for x in parsers:
            x["active"] = False
    elif not parsers:
        item["active"] = True
    parsers.append(item)
    return _save_integrations(store[INTEGRATIONS_KEY]["llms"], parsers, actor=actor, action="create_parser", key=item["id"])


def update_parser(parser_id: str, body: dict[str, Any], *, actor: str = "admin") -> dict[str, Any]:
    store = _ensure_integrations(_read_raw_store())
    parsers = list(store[INTEGRATIONS_KEY]["parsers"])
    idx = next((i for i, x in enumerate(parsers) if x["id"] == parser_id), None)
    if idx is None:
        raise KeyError(parser_id)
    cur = {**parsers[idx]}
    for field in ("name", "base_url", "country_code", "source_code"):
        if field in body and body[field] is not None:
            val = str(body[field]).strip()
            if field == "source_code":
                val = val.upper().replace(" ", "_")
            if field == "country_code":
                val = val.upper()[:2]
            cur[field] = val
    if "token" in body and body["token"] is not None and str(body["token"]).strip() != "":
        cur["token"] = str(body["token"]).strip()
    if "active" in body:
        cur["active"] = bool(body["active"])
        if cur["active"]:
            for x in parsers:
                x["active"] = False
    parsers[idx] = cur
    return _save_integrations(store[INTEGRATIONS_KEY]["llms"], parsers, actor=actor, action="update_parser", key=parser_id)


def delete_parser(parser_id: str, *, actor: str = "admin") -> dict[str, Any]:
    store = _ensure_integrations(_read_raw_store())
    parsers = [x for x in store[INTEGRATIONS_KEY]["parsers"] if x["id"] != parser_id]
    if not parsers:
        raise ValueError("Cannot delete the last parser")
    if not any(x.get("active") for x in parsers):
        parsers[0]["active"] = True
    return _save_integrations(store[INTEGRATIONS_KEY]["llms"], parsers, actor=actor, action="delete_parser", key=parser_id)


def activate_parser(parser_id: str, *, actor: str = "admin") -> dict[str, Any]:
    return update_parser(parser_id, {"active": True}, actor=actor)


def get_active_parser_raw(source_code: str | None = None) -> dict[str, Any] | None:
    store = _ensure_integrations(_read_raw_store())
    parsers = store[INTEGRATIONS_KEY]["parsers"]
    if source_code:
        match = next((x for x in parsers if x.get("source_code") == source_code), None)
        if match:
            return match
    return next((x for x in parsers if x.get("active")), parsers[0] if parsers else None)


# ── Legacy flat config API (still used by overview chips) ────────────────────


def list_config(*, include_values: bool = False) -> list[dict[str, Any]]:
    catalog = [
        {"key": "LLM_API_KEY", "label": "LLM API Key", "category": "llm", "secret": True},
        {"key": "LLM_BASE_URL", "label": "LLM Base URL", "category": "llm", "secret": False, "default": "https://api.openai.com/v1"},
        {"key": "LLM_MODEL", "label": "LLM Model", "category": "llm", "secret": False, "default": "gpt-5.6-terra"},
        {"key": "LLM_PROVIDER", "label": "LLM Provider", "category": "llm", "secret": False, "default": "openai"},
        {"key": "GOSZAKUP_TOKEN", "label": "Goszakup Token", "category": "ingestion", "secret": True},
        {"key": "GOSZAKUP_BASE_URL", "label": "Goszakup Base URL", "category": "ingestion", "secret": False, "default": "https://ows.goszakup.gov.kz"},
    ]
    rows = []
    for item in catalog:
        key = item["key"]
        raw = get_config_value(key, item.get("default"))
        entry = {
            **item,
            "configured": bool(raw and str(raw).strip()),
            "source": "runtime" if raw else "empty",
            "description": "",
        }
        if item["secret"]:
            entry["value_masked"] = mask_secret(raw) if raw else None
            if include_values:
                entry["value"] = raw
        else:
            entry["value"] = raw
            entry["value_masked"] = raw
        rows.append(entry)
    return rows


def set_config_value(key: str, value: str, *, actor: str = "admin") -> dict[str, Any]:
    if key not in FLAT_KEYS:
        raise KeyError(f"Unknown config key: {key}")
    store = _ensure_integrations(_read_raw_store())
    store[key] = value.strip()
    # mirror into active integration
    if key.startswith("LLM_"):
        llms = store[INTEGRATIONS_KEY]["llms"]
        active = next((x for x in llms if x.get("active")), None)
        if active:
            mapping = {
                "LLM_API_KEY": "api_key",
                "LLM_BASE_URL": "base_url",
                "LLM_MODEL": "model",
                "LLM_PROVIDER": "provider",
            }
            active[mapping[key]] = value.strip()
    if key.startswith("GOSZAKUP_"):
        parsers = store[INTEGRATIONS_KEY]["parsers"]
        active = next((x for x in parsers if x.get("active")), None)
        if active:
            mapping = {"GOSZAKUP_TOKEN": "token", "GOSZAKUP_BASE_URL": "base_url"}
            active[mapping[key]] = value.strip()
    _write_store(store)
    _audit("set", key, actor, mask_secret(value) if "KEY" in key or "TOKEN" in key else value)
    return next(r for r in list_config() if r["key"] == key)


def delete_config_value(key: str, *, actor: str = "admin") -> dict[str, Any]:
    if key not in FLAT_KEYS:
        raise KeyError(f"Unknown config key: {key}")
    store = _ensure_integrations(_read_raw_store())
    store.pop(key, None)
    _write_store(store)
    _audit("delete", key, actor)
    return next(r for r in list_config() if r["key"] == key)


def list_audit(limit: int = 50) -> list[dict[str, Any]]:
    client = _redis()
    if not client:
        return []
    try:
        raw = client.lrange(REDIS_AUDIT, 0, max(0, limit - 1))
        return [json.loads(x) for x in raw]
    except Exception:  # noqa: BLE001
        return []
