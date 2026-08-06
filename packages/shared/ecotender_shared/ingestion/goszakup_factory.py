"""Resolve goszakup SourceAdapter (OWS API vs Playwright stub vs fixtures)."""

from __future__ import annotations

import os

from ecotender_shared.ingestion.base import SourceAdapter
from ecotender_shared.ingestion.goszakup_playwright import (
    KazakhstanGoszakupPlaywrightAdapter,
    should_use_playwright_stub,
)


def resolve_goszakup_adapter(source_code: str) -> SourceAdapter:
    """Pick OWS v3 or Playwright stub based on source_code and env."""
    force_playwright = source_code in (
        "KZ_GOSZAKUP_PLAYWRIGHT",
        "goszakup_playwright",
        "playwright",
    )
    if force_playwright or should_use_playwright_stub():
        return KazakhstanGoszakupPlaywrightAdapter()

    from ecotender_shared.ingestion.goszakup_kz import KazakhstanGoszakupAdapter

    return KazakhstanGoszakupAdapter(
        limit=int(os.getenv("GOSZAKUP_PAGE_LIMIT", "50")),
        max_pages=int(os.getenv("GOSZAKUP_MAX_PAGES", "3")),
    )
