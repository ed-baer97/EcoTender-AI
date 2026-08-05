"""Runtime config / API keys — Redis + JSON file, with env fallback.

Admin panel writes here so LLM / goszakup pick up keys without recreating containers.
Values in Redis take precedence over process environment.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

REDIS_HASH = "ecotender:runtime_config"
REDIS_AUDIT = "ecotender:runtime_config:audit"
DEFAULT_FILE = Path(os.getenv("RUNTIME_CONFIG_PATH", "/data/runtime/config.json"))

# Catalog shown in admin UI (and allowed to write)
CONFIG_CATALOG: list[dict[str, Any]] = [
    {
        "key": "LLM_API_KEY",
        "label": "LLM API Key",
        "category": "llm",
        "secret": True,
        "description": "Bearer-ключ для OpenAI-compatible API (объяснение Risk Score)",
        "placeholder": "sk-...",
    },
    {
        "key": "LLM_BASE_URL",
        "label": "LLM Base URL",
        "category": "llm",
        "secret": False,
        "description": "Базовый URL chat/completions",
        "placeholder": "https://api.openai.com/v1",
        "default": "https://api.openai.com/v1",
    },
    {
        "key": "LLM_MODEL",
        "label": "LLM Model",
        "category": "llm",
        "secret": False,
        "description": "Имя модели для explain",
        "placeholder": "gpt-5.6-terra",
        "default": "gpt-5.6-terra",
    },
    {
        "key": "LLM_PROVIDER",
        "label": "LLM Provider",
        "category": "llm",
        "secret": False,
        "description": "Метка провайдера (openai / deepseek / openrouter)",
        "placeholder": "openai",
        "default": "openai",
    },
    {
        "key": "GOSZAKUP_TOKEN",
        "label": "Goszakup OWS Token",
        "category": "ingestion",
        "secret": True,
        "description": "Bearer-токен goszakup.gov.kz OWS v3 (Профиль → Выпуск токена)",
        "placeholder": "",
    },
    {
        "key": "GOSZAKUP_BASE_URL",
        "label": "Goszakup Base URL",
        "category": "ingestion",
        "secret": False,
        "description": "Базовый URL OWS API",
        "placeholder": "https://ows.goszakup.gov.kz",
        "default": "https://ows.goszakup.gov.kz",
    },
]

ALLOWED_KEYS = {item["key"] for item in CONFIG_CATALOG}


def _redis():
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis

        return redis.from_url(url, decode_responses=True, socket_connect_timeout=1.5)
    except Exception:  # noqa: BLE001
        return None


def _load_file(path: Path = DEFAULT_FILE) -> dict[str, str]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v is not None}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_file(values: dict[str, str], path: Path = DEFAULT_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")


def bootstrap_from_file() -> None:
    """Load JSON into Redis on gateway startup (idempotent merge: Redis wins if key exists)."""
    client = _redis()
    file_vals = _load_file()
    if not client or not file_vals:
        return
    try:
        existing = client.hgetall(REDIS_HASH) or {}
        for k, v in file_vals.items():
            if k not in existing:
                client.hset(REDIS_HASH, k, v)
    except Exception:  # noqa: BLE001
        return


def get_config_value(key: str, default: str | None = None) -> str | None:
    """Resolve: Redis → file → env → default."""
    client = _redis()
    if client:
        try:
            val = client.hget(REDIS_HASH, key)
            if val is not None and str(val).strip() != "":
                return str(val)
        except Exception:  # noqa: BLE001
            pass

    file_vals = _load_file()
    if key in file_vals and str(file_vals[key]).strip() != "":
        return file_vals[key]

    env = os.getenv(key)
    if env is not None and str(env).strip() != "":
        return env
    return default


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:4]}…{value[-4:]}"


def list_config(*, include_values: bool = False) -> list[dict[str, Any]]:
    """Public list for admin UI (secrets masked unless include_values)."""
    rows = []
    for item in CONFIG_CATALOG:
        key = item["key"]
        raw = get_config_value(key, item.get("default"))
        source = _value_source(key, raw)
        entry = {
            **item,
            "configured": bool(raw and str(raw).strip()),
            "source": source,
            "updated_at": _meta_get(key, "updated_at"),
            "updated_by": _meta_get(key, "updated_by"),
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


def _meta_key(key: str) -> str:
    return f"ecotender:runtime_config:meta:{key}"


def _meta_get(key: str, field: str) -> str | None:
    client = _redis()
    if not client:
        return None
    try:
        return client.hget(_meta_key(key), field)
    except Exception:  # noqa: BLE001
        return None


def _value_source(key: str, resolved: str | None) -> str:
    if not resolved:
        return "empty"
    client = _redis()
    if client:
        try:
            if client.hget(REDIS_HASH, key):
                return "runtime"
        except Exception:  # noqa: BLE001
            pass
    if key in _load_file():
        return "file"
    if os.getenv(key):
        return "env"
    return "default"


def set_config_value(key: str, value: str, *, actor: str = "admin") -> dict[str, Any]:
    if key not in ALLOWED_KEYS:
        raise KeyError(f"Unknown config key: {key}")
    value = value.strip()
    client = _redis()
    file_vals = _load_file()
    file_vals[key] = value
    _save_file(file_vals)

    if client:
        client.hset(REDIS_HASH, key, value)
        client.hset(
            _meta_key(key),
            mapping={"updated_at": str(int(time.time())), "updated_by": actor},
        )
        client.lpush(
            REDIS_AUDIT,
            json.dumps(
                {"ts": int(time.time()), "action": "set", "key": key, "actor": actor, "masked": mask_secret(value)},
                ensure_ascii=False,
            ),
        )
        client.ltrim(REDIS_AUDIT, 0, 199)

    return next(r for r in list_config() if r["key"] == key)


def delete_config_value(key: str, *, actor: str = "admin") -> dict[str, Any]:
    if key not in ALLOWED_KEYS:
        raise KeyError(f"Unknown config key: {key}")
    client = _redis()
    file_vals = _load_file()
    file_vals.pop(key, None)
    _save_file(file_vals)

    if client:
        client.hdel(REDIS_HASH, key)
        client.delete(_meta_key(key))
        client.lpush(
            REDIS_AUDIT,
            json.dumps(
                {"ts": int(time.time()), "action": "delete", "key": key, "actor": actor},
                ensure_ascii=False,
            ),
        )
        client.ltrim(REDIS_AUDIT, 0, 199)

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
