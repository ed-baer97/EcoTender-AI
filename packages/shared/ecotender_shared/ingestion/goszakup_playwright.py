"""Kazakhstan goszakup.gov.kz — Playwright crawler over public portal."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urljoin

from ecotender_shared.ingestion.base import RawTenderPage, SourceAdapter
from ecotender_shared.ingestion.eco_filter import (
    classify_eco_category,
    is_eco_related,
    is_mangystau_related,
    map_kz_region,
)
from ecotender_shared.ingestion.goszakup_html import (
    PORTAL_BASE,
    _ANNO_RE,
    parse_announce_detail,
    parse_bidders_table,
    parse_contracts_table,
    parse_detail_overview,
    parse_documentation_groups,
    parse_documents_table,
    parse_lots_table,
    parse_modal_files,
    parse_results_table,
    parse_search_list,
    parse_search_next_page,
)
from ecotender_shared.schemas import NormalizedTender

SEARCH_PATH = "/ru/search/announce"
SEARCH_FILTER_KEYS = (
    "name",
    "customer",
    "number",
    "year",
    "amount_from",
    "amount_to",
    "trade_type",
    "type",
    "start_date_from",
    "start_date_to",
    "end_date_from",
    "end_date_to",
    "itog_date_from",
    "itog_date_to",
    "smb",
    "kato",
    "status",  # filter[status][] — e.g. 350=Завершено
    "signs",  # filter[signs][] — e.g. is_not_active
)
# Multi-value portal fields use filter[key][]=
SEARCH_MULTI_KEYS = frozenset({"status", "signs"})

# Open / accepting-bids announce statuses to drop in post-filter (portal labels).
OPEN_ANNOUNCE_STATUS_MARKERS = (
    "прием заявок",
    "приём заявок",
    "прием ценовых",
    "приём ценовых",
    "дополнение заявок",
    "опубликовано (прием",
    "опубликовано (приём",
    "рассмотрение заявок",
    "рассмотрение дополнений",
    "формирование протокола",
)

# Default: completed announces only (portal value 350 = «Завершено»).
DEFAULT_ANNOUNCE_STATUS = "350"
DEFAULT_ANNOUNCE_SIGNS = "is_not_active"
# Contract statuses on detail tab (substring match, case-insensitive).
DEFAULT_CONTRACT_STATUSES = "действует,исполнен"

# Мангистауская область (КАТО НК РК)
MANGYSTAU_KATO = "470000000"

DOMAIN_PRESETS: dict[str, dict[str, Any]] = {
    "ecology": {
        "name": "Экология",
        "amount_from": "1000000",
        "trade_type": "r",
        "keywords": ["эколог", "экология", "охрана окружающей среды"],
    },
    "oil_spill": {
        "name": "нефт",
        "amount_from": "1000000",
        "trade_type": "r",
        "keywords": ["нефт", "нефтезагряз", "бонов", "разлив"],
    },
    "water_monitoring": {
        "name": "мониторинг воды",
        "amount_from": "500000",
        "trade_type": "r",
        "keywords": ["монитор", "морской воды", "лаборатор"],
    },
    "dredging": {
        "name": "дноуглуб",
        "amount_from": "1000000",
        "trade_type": "r",
        "keywords": ["дноуглуб", "порт", "канал"],
    },
    "reclamation": {
        "name": "рекультивац",
        "amount_from": "1000000",
        "trade_type": "r",
        "keywords": ["рекультив", "утилизац", "очистк"],
    },
}


def _fixture_dir() -> Path:
    candidates = [
        Path("/data/fixtures/html"),
        Path(__file__).resolve().parents[4] / "data" / "fixtures" / "html",
    ]
    return next((p for p in candidates if p.exists()), candidates[-1])


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


@dataclass
class SearchConfig:
    filters: dict[str, str]
    matched_keywords: list[str]
    preset: str | None = None

    def to_query(self) -> str:
        pairs: list[tuple[str, str]] = []
        for key, value in self.filters.items():
            if value is None or str(value).strip() == "":
                continue
            if key in SEARCH_MULTI_KEYS:
                for part in str(value).split(","):
                    part = part.strip()
                    if part:
                        pairs.append((f"filter[{key}][]", part))
            else:
                pairs.append((f"filter[{key}]", str(value)))
        return urlencode(pairs)


class KazakhstanGoszakupPlaywrightAdapter(SourceAdapter):
    source_code = "KZ_GOSZAKUP_PLAYWRIGHT"
    country_code = "KZ"
    mode = "playwright_stub"

    def __init__(
        self,
        *,
        keyword: str | None = None,
        max_items: int | None = None,
        fetch_detail: bool | None = None,
        offline: bool | None = None,
        prefer_caspian: bool = True,
        portal_base: str | None = None,
    ) -> None:
        self.keyword = keyword if keyword is not None else os.getenv("GOSZAKUP_PW_KEYWORD", "экология")
        self.keywords = self._load_keywords()
        self.max_items = max_items or int(os.getenv("GOSZAKUP_PW_MAX_ITEMS", "50"))
        self.max_pages = int(os.getenv("GOSZAKUP_PW_MAX_PAGES", "5"))
        self.eco_only = _env_bool("GOSZAKUP_PW_ECO_ONLY", True)
        self.min_amount = float(os.getenv("GOSZAKUP_PW_FILTER_AMOUNT_FROM") or os.getenv("GOSZAKUP_PW_MIN_AMOUNT") or "1000000")
        # Default: only Мангистауская область (hackathon scope). Set GOSZAKUP_PW_REGION_ONLY=off to disable.
        region_only = (os.getenv("GOSZAKUP_PW_REGION_ONLY", "mangystau") or "mangystau").strip().lower()
        self.region_only = None if region_only in ("", "0", "false", "no", "off", "all", "none") else region_only
        # Completed / inactive announces (not open for bids). Set env to empty to disable.
        if "GOSZAKUP_PW_FILTER_STATUS" in os.environ:
            self.announce_status = (os.environ.get("GOSZAKUP_PW_FILTER_STATUS") or "").strip()
        else:
            self.announce_status = DEFAULT_ANNOUNCE_STATUS
        if "GOSZAKUP_PW_FILTER_SIGNS" in os.environ:
            self.announce_signs = (os.environ.get("GOSZAKUP_PW_FILTER_SIGNS") or "").strip()
        else:
            self.announce_signs = DEFAULT_ANNOUNCE_SIGNS
        # Require contract tab status ∈ действует|исполнен (and Передан.* variants).
        self.contract_statuses = [
            x.strip().lower()
            for x in (os.getenv("GOSZAKUP_PW_CONTRACT_STATUSES", DEFAULT_CONTRACT_STATUSES) or "").split(",")
            if x.strip()
        ]
        self.require_contract_status = _env_bool(
            "GOSZAKUP_PW_REQUIRE_CONTRACT_STATUS",
            False if (offline if offline is not None else _env_bool("GOSZAKUP_PW_OFFLINE", False)) else True,
        )
        # If True, empty contracts table rejects the tender. Default False: empty → allow when announce is «Завершено».
        self.require_contract_rows = _env_bool("GOSZAKUP_PW_REQUIRE_CONTRACT_ROWS", False)
        self.download_docs = _env_bool("GOSZAKUP_PW_DOWNLOAD_DOCS", True)
        self.max_docs = int(os.getenv("GOSZAKUP_PW_MAX_DOCS", "8"))
        self.extract_on_ingest = _env_bool("GOSZAKUP_PW_EXTRACT_ON_INGEST", False)
        self.search_presets = self._load_presets()
        self.fetch_detail = (
            fetch_detail if fetch_detail is not None else _env_bool("GOSZAKUP_PW_FETCH_DETAIL", True)
        )
        self.offline = offline if offline is not None else _env_bool("GOSZAKUP_PW_OFFLINE", False)
        self.prefer_caspian = prefer_caspian
        self.portal_base = (portal_base or os.getenv("GOSZAKUP_PORTAL_URL", PORTAL_BASE)).rstrip("/")
        self.fixture_dir = _fixture_dir()
        self._cache: dict[str, dict[str, Any]] = {}
        self._active_search_config: SearchConfig | None = None

    def _load_keywords(self) -> list[str | None]:
        extra = os.getenv("GOSZAKUP_PW_KEYWORDS", "")
        terms: list[str | None] = []
        # Nationwide "recent" browse floods non-Mangystau noise — only when region filter is off.
        browse_default = "false" if (os.getenv("GOSZAKUP_PW_REGION_ONLY", "mangystau") or "").lower() in (
            "mangystau",
            "man",
            "kz-man",
            "caspian",
        ) else "true"
        if _env_bool("GOSZAKUP_PW_BROWSE_RECENT", browse_default == "true"):
            terms.append(None)
        primary = (self.keyword or "").strip()
        if primary and primary not in ("*", "all"):
            terms.append(primary)
        for part in extra.split(","):
            part = part.strip()
            if part and part not in terms:
                terms.append(part)
        if not terms:
            terms.append(None)
        return terms

    def _load_presets(self) -> list[str]:
        raw = os.getenv("GOSZAKUP_PW_PRESETS", "ecology,oil_spill,water_monitoring,dredging,reclamation")
        out = [x.strip() for x in raw.split(",") if x.strip()]
        return out or ["ecology"]

    def _env_search_filters(self) -> dict[str, str]:
        out: dict[str, str] = {}
        env_map = {
            "name": "GOSZAKUP_PW_FILTER_NAME",
            "customer": "GOSZAKUP_PW_FILTER_CUSTOMER",
            "number": "GOSZAKUP_PW_FILTER_NUMBER",
            "year": "GOSZAKUP_PW_FILTER_YEAR",
            "amount_from": "GOSZAKUP_PW_FILTER_AMOUNT_FROM",
            "amount_to": "GOSZAKUP_PW_FILTER_AMOUNT_TO",
            "trade_type": "GOSZAKUP_PW_FILTER_TRADE_TYPE",
            "type": "GOSZAKUP_PW_FILTER_TYPE",
            "start_date_from": "GOSZAKUP_PW_FILTER_START_DATE_FROM",
            "start_date_to": "GOSZAKUP_PW_FILTER_START_DATE_TO",
            "end_date_from": "GOSZAKUP_PW_FILTER_END_DATE_FROM",
            "end_date_to": "GOSZAKUP_PW_FILTER_END_DATE_TO",
            "itog_date_from": "GOSZAKUP_PW_FILTER_ITOG_DATE_FROM",
            "itog_date_to": "GOSZAKUP_PW_FILTER_ITOG_DATE_TO",
            "smb": "GOSZAKUP_PW_FILTER_SMB",
            "kato": "GOSZAKUP_PW_FILTER_KATO",
            "status": "GOSZAKUP_PW_FILTER_STATUS",
            "signs": "GOSZAKUP_PW_FILTER_SIGNS",
        }
        for key, env_name in env_map.items():
            if env_name not in os.environ:
                continue
            value = os.environ.get(env_name)
            if value is None:
                continue
            # Empty string means "explicitly unset this filter".
            if str(value).strip() == "":
                continue
            out[key] = value
        return out

    def _default_lifecycle_filters(self) -> dict[str, str]:
        """Prefer finished announces — not open bid windows."""
        out: dict[str, str] = {}
        if self.announce_status:
            out["status"] = self.announce_status
        if self.announce_signs:
            out["signs"] = self.announce_signs
        return out

    def _with_lifecycle(self, filters: dict[str, str]) -> dict[str, str]:
        merged = dict(filters)
        for k, v in self._default_lifecycle_filters().items():
            merged.setdefault(k, v)
        return merged

    def _build_search_configs(self) -> list[SearchConfig]:
        env_filters = self._env_search_filters()
        configs: list[SearchConfig] = []
        mangystau_customer = os.getenv("GOSZAKUP_PW_FILTER_CUSTOMER") or "Мангистау"
        mangystau_kato = os.getenv("GOSZAKUP_PW_FILTER_KATO") or MANGYSTAU_KATO
        amount_from = os.getenv("GOSZAKUP_PW_FILTER_AMOUNT_FROM") or "1000000"
        if self.region_only in ("mangystau", "man", "kz-man"):
            # Official region facet on the portal + amount floor + completed lifecycle.
            configs.append(
                SearchConfig(
                    filters=self._with_lifecycle({"kato": mangystau_kato, "amount_from": amount_from}),
                    matched_keywords=["мангистау", "актау", "курык", "жанаозен"],
                    preset="mangystau_kato",
                )
            )
            configs.append(
                SearchConfig(
                    filters=self._with_lifecycle({"customer": mangystau_customer, "amount_from": amount_from}),
                    matched_keywords=["мангистау", "актау", "курык", "жанаозен"],
                    preset="mangystau_customer",
                )
            )
            for name_term in ("мангистау", "актау", "курык", "жанаозен"):
                configs.append(
                    SearchConfig(
                        filters=self._with_lifecycle({"name": name_term, "amount_from": amount_from}),
                        matched_keywords=[name_term],
                        preset=f"mangystau_name_{name_term}",
                    )
                )
        if env_filters:
            matched = [x for x in self.keywords if x]
            filters = self._with_lifecycle(dict(env_filters))
            if filters.get("name") is None and self.keyword and "name" not in filters:
                filters["name"] = self.keyword
            if self.region_only in ("mangystau", "man", "kz-man") and "customer" not in filters:
                filters["customer"] = mangystau_customer
            configs.append(SearchConfig(filters=filters, matched_keywords=matched))
        for preset_name in self.search_presets:
            preset = DOMAIN_PRESETS.get(preset_name)
            if not preset:
                continue
            filters = {k: str(v) for k, v in preset.items() if k in SEARCH_FILTER_KEYS and v}
            filters = self._with_lifecycle(filters)
            if self.region_only in ("mangystau", "man", "kz-man"):
                filters.setdefault("customer", mangystau_customer)
            matched = [str(x) for x in preset.get("keywords", [])]
            configs.append(SearchConfig(filters=filters, matched_keywords=matched, preset=preset_name))
        if not configs:
            filters = {"name": self.keyword} if self.keyword else {}
            if self.region_only in ("mangystau", "man", "kz-man"):
                filters["customer"] = mangystau_customer
            configs.append(
                SearchConfig(
                    filters=self._with_lifecycle(filters),
                    matched_keywords=[self.keyword] if self.keyword else [],
                )
            )
        return configs

    def _search_url(self, *, search_config: SearchConfig | None = None, keyword: str | None = None) -> str:
        if search_config is not None:
            query = search_config.to_query()
            return f"{self.portal_base}{SEARCH_PATH}?{query}" if query else f"{self.portal_base}{SEARCH_PATH}"
        term = keyword if keyword is not None else self.keyword
        if term and str(term).strip() not in ("*", "all"):
            q = quote(str(term).strip())
            return f"{self.portal_base}{SEARCH_PATH}?filter%5Bname%5D={q}"
        return f"{self.portal_base}{SEARCH_PATH}"

    def _passes_filter(self, item: dict[str, Any]) -> bool:
        blob = " ".join(
            str(item.get(k) or "")
            for k in ("name_ru", "org_name_ru", "customer_name_ru", "number_anno", "org_address")
        )
        matched = [
            kw
            for kw in (self._active_search_config.matched_keywords if self._active_search_config else [])
            if kw and kw.lower() in blob.lower()
        ]
        item["matched_keywords"] = matched

        status_label = str(item.get("status_label") or "").lower()
        if status_label and any(m in status_label for m in OPEN_ANNOUNCE_STATUS_MARKERS):
            return False
        # When we request completed announces, drop obvious open labels even if portal leaks them.
        if self.announce_status and status_label:
            if "завершен" not in status_label and any(
                x in status_label for x in ("опубликовано", "прием", "приём", "рассмотрение")
            ):
                return False

        amount = item.get("total_sum")
        try:
            amount_f = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            amount_f = None
        if amount_f is not None and self.min_amount > 0 and amount_f < self.min_amount:
            return False

        if self.region_only in ("mangystau", "man", "kz-man"):
            preset = (self._active_search_config.preset if self._active_search_config else None) or ""
            filters = (self._active_search_config.filters if self._active_search_config else {}) or {}
            kato = str(filters.get("kato") or "")
            # KATO/customer region searches are authoritative; name searches still need text hints.
            if preset in ("mangystau_kato", "mangystau_customer") or kato.startswith("47"):
                item["region_forced"] = "KZ-MAN"
                return True
            if not is_mangystau_related(blob):
                return False
            if preset.startswith("mangystau"):
                return True
        elif self.region_only in ("caspian",) or self.prefer_caspian:
            from ecotender_shared.ingestion.eco_filter import is_caspian_kz_related

            if not is_caspian_kz_related(blob):
                return False
        if not self.eco_only:
            return True
        return is_eco_related(blob) or bool(matched)

    def _contracts_match_required_status(self, contracts: list[dict[str, Any]]) -> bool:
        if not self.require_contract_status or not self.contract_statuses:
            return True
        if not contracts:
            return not self.require_contract_rows
        for row in contracts:
            blob = " ".join(
                str(x or "")
                for x in (
                    row.get("status"),
                    row.get("name"),
                    json.dumps(row.get("raw") or {}, ensure_ascii=False),
                )
            ).lower()
            if any(tok in blob for tok in self.contract_statuses):
                return True
        return False

    def _should_ingest(
        self,
        *,
        contracts: list[dict[str, Any]],
        status_label: str | None,
    ) -> tuple[bool, str | None]:
        """Return (ok, skip_reason)."""
        if not self.require_contract_status:
            return True, None
        label = (status_label or "").lower()
        if contracts:
            if self._contracts_match_required_status(contracts):
                return True, None
            return False, "contract_status_not_active_or_executed"
        # No contract rows: accept completed announces unless rows are mandatory.
        if self.require_contract_rows:
            return False, "contracts_table_empty"
        if "завершен" in label or not label:
            return True, None
        if any(m in label for m in OPEN_ANNOUNCE_STATUS_MARKERS):
            return False, "open_announce_no_contracts"
        return True, None

    def _load_offline_list_html(self) -> str:
        path = self.fixture_dir / "goszakup_search_list.html"
        if not path.exists():
            raise FileNotFoundError(
                f"Offline HTML fixture missing: {path}. "
                "Set GOSZAKUP_PW_OFFLINE=false to use Playwright against the portal."
            )
        return path.read_text(encoding="utf-8")

    def _fetch_html_playwright(
        self, url: str, *, submit_search: bool = False, search_term: str | None = None
    ) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright is not installed. pip install playwright && playwright install chromium"
            ) from exc

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=_env_bool("GOSZAKUP_PW_HEADLESS", True))
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (compatible; EcoTenderAI/1.0; +https://github.com/ecotender) "
                    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page.set_default_timeout(int(os.getenv("GOSZAKUP_PW_TIMEOUT_MS", "45000")))
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_selector("a[href*='/announce/index/']", timeout=20000)
            except Exception:
                pass

            html = page.content()
            browser.close()
            return html

    def _fetch_bundle_playwright(self, announce_id: str, *, detail_url: str | None = None) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright is not installed. pip install playwright && playwright install chromium"
            ) from exc

        url = detail_url or f"{self.portal_base}/ru/announce/index/{announce_id}"
        tab_wait_ms = int(os.getenv("GOSZAKUP_PW_TAB_WAIT_MS", "400"))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=_env_bool("GOSZAKUP_PW_HEADLESS", True))
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (compatible; EcoTenderAI/1.0; +https://github.com/ecotender) "
                    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page.set_default_timeout(int(os.getenv("GOSZAKUP_PW_TIMEOUT_MS", "25000")))
            page.goto(url, wait_until="domcontentloaded")
            # Avoid networkidle — often hangs 15s+ on goszakup analytics/widgets.
            page.wait_for_timeout(500)

            detail_html = page.content()
            overview = parse_detail_overview(detail_html, announce_id=announce_id)
            status_label = str(overview.get("status_label") or "")

            tabs: list[dict[str, Any]] = []
            documents: list[dict[str, Any]] = []
            lots: list[dict[str, Any]] = []
            documentation_groups: list[dict[str, Any]] = []
            contracts: list[dict[str, Any]] = parse_contracts_table(detail_html, base_url=self.portal_base)
            raw_assets: list[dict[str, Any]] = [
                {
                    "kind": "detail_html",
                    "name": f"announce_{announce_id}.html",
                    "content_type": "text/html; charset=utf-8",
                    "source_url": url,
                    "tab_name": "detail",
                    "body_b64": base64.b64encode(detail_html.encode("utf-8")).decode("ascii"),
                }
            ]

            tab_loc = page.locator(".nav-tabs a, .nav li a, [role='tab']")
            seen_names: set[str] = set()
            tab_html_by_name: dict[str, str] = {}

            # Prefer contracts / results tabs first for early skip.
            tab_indices = list(range(min(tab_loc.count(), 12)))

            def _tab_priority(i: int) -> int:
                try:
                    name = (tab_loc.nth(i).inner_text(timeout=1000) or "").strip().lower()
                except Exception:
                    name = ""
                if "договор" in name:
                    return 0
                if "итог" in name or "результат" in name:
                    return 1
                if "лот" in name:
                    return 2
                if "документ" in name:
                    return 3
                return 5

            tab_indices.sort(key=_tab_priority)

            for idx in tab_indices:
                loc = tab_loc.nth(idx)
                try:
                    name = (loc.inner_text(timeout=1500) or "").strip()
                except Exception:
                    name = ""
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                try:
                    loc.click(timeout=3000)
                    page.wait_for_timeout(tab_wait_ms)
                except Exception:
                    pass
                tab_html = page.content()
                tab_html_by_name[name.lower()] = tab_html
                tab_slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_") or f"tab_{idx}"
                tabs.append({"name": name, "slug": tab_slug, "html_len": len(tab_html), "source_url": page.url})
                raw_assets.append(
                    {
                        "kind": "tab_html",
                        "name": f"announce_{announce_id}_{tab_slug}.html",
                        "content_type": "text/html; charset=utf-8",
                        "source_url": page.url,
                        "tab_name": name,
                        "body_b64": base64.b64encode(tab_html.encode("utf-8")).decode("ascii"),
                    }
                )
                if "договор" in name.lower():
                    contracts = parse_contracts_table(tab_html, base_url=self.portal_base) or contracts
                for doc in parse_documents_table(tab_html, base_url=self.portal_base):
                    documents.append({**doc, "tab_name": name, "tab_slug": tab_slug})
                if "лот" in name.lower():
                    lots.extend(parse_lots_table(tab_html))
                if "документ" in name.lower():
                    documentation_groups = parse_documentation_groups(tab_html)

                # Early exit: after first contracts tab (or enough tabs), decide skip before heavy downloads.
                if "договор" in name.lower() or len(seen_names) >= 3:
                    ok, skip_reason = self._should_ingest(contracts=contracts, status_label=status_label)
                    if not ok:
                        browser.close()
                        return {
                            "detail_html": detail_html,
                            "tabs": tabs,
                            "documents": documents,
                            "lots": lots,
                            "contracts": contracts,
                            "documentation_groups": documentation_groups,
                            "raw_assets": raw_assets,
                            "detail_url": url,
                            "skip_reason": skip_reason,
                            "status_label": status_label,
                            "overview": overview,
                        }

            ok, skip_reason = self._should_ingest(contracts=contracts, status_label=status_label)
            if not ok:
                browser.close()
                return {
                    "detail_html": detail_html,
                    "tabs": tabs,
                    "documents": documents,
                    "lots": lots,
                    "contracts": contracts,
                    "documentation_groups": documentation_groups,
                    "raw_assets": raw_assets,
                    "detail_url": url,
                    "skip_reason": skip_reason,
                    "status_label": status_label,
                    "overview": overview,
                }

            # Heavy path: documentation groups + file downloads (only for keepers).
            if self.download_docs and not documentation_groups:
                docs_url = f"{self.portal_base}/ru/announce/index/{announce_id}?tab=documents"
                try:
                    page.goto(docs_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(tab_wait_ms)
                    docs_html = page.content()
                    documentation_groups = parse_documentation_groups(docs_html)
                    for doc in parse_documents_table(docs_html, base_url=self.portal_base):
                        documents.append({**doc, "tab_name": "Документация", "tab_slug": "dokumentatsiya"})
                    raw_assets.append(
                        {
                            "kind": "tab_html",
                            "name": f"announce_{announce_id}_dokumentatsiya.html",
                            "content_type": "text/html; charset=utf-8",
                            "source_url": docs_url,
                            "tab_name": "Документация",
                            "body_b64": base64.b64encode(docs_html.encode("utf-8")).decode("ascii"),
                        }
                    )
                except Exception:
                    pass

            if self.download_docs:
                for group in documentation_groups[:6]:
                    group_id = group.get("group_id")
                    if not group_id:
                        continue
                    modal_url = f"{self.portal_base}/ru/announce/actionAjaxModalShowFiles/{announce_id}/{group_id}"
                    try:
                        resp = page.context.request.get(modal_url, timeout=12000)
                        if not resp.ok:
                            group["modal_error"] = f"http_{resp.status}"
                            continue
                        modal_html = resp.text()
                        group["modal_url"] = modal_url
                        raw_assets.append(
                            {
                                "kind": "modal_html",
                                "name": f"announce_{announce_id}_files_{group_id}.html",
                                "content_type": "text/html; charset=utf-8",
                                "source_url": modal_url,
                                "tab_name": group.get("name") or "Документация",
                                "body_b64": base64.b64encode(modal_html.encode("utf-8")).decode("ascii"),
                            }
                        )
                        modal_docs = parse_modal_files(modal_html, base_url=self.portal_base)
                        for doc in modal_docs:
                            documents.append(
                                {
                                    **doc,
                                    "tab_name": "Документация",
                                    "tab_slug": "dokumentatsiya",
                                    "group_id": group_id,
                                    "group_name": group.get("name"),
                                    "kind": "specification"
                                    if "спецификац" in (group.get("name") or "").lower()
                                    or "тс" in (doc.get("name") or "").lower()
                                    else doc.get("kind") or "document",
                                }
                            )
                    except Exception as exc:
                        group["modal_error"] = str(exc)

            if not documents:
                for doc in parse_documents_table(detail_html, base_url=self.portal_base):
                    documents.append({**doc, "tab_name": "detail", "tab_slug": "detail"})
            if not lots:
                lots = parse_lots_table(detail_html)
                for html in tab_html_by_name.values():
                    if not lots:
                        lots = parse_lots_table(html)

            dedup: dict[str, dict[str, Any]] = {}
            for doc in documents:
                key = str(doc.get("url") or doc.get("name") or id(doc))
                dedup.setdefault(key, doc)
            documents = list(dedup.values())

            # Prefer specifications first, then cap downloads.
            def _doc_rank(d: dict[str, Any]) -> tuple[int, str]:
                kind = str(d.get("kind") or "")
                name = str(d.get("name") or "").lower()
                group = str(d.get("group_name") or "").lower()
                is_spec = kind == "specification" or "спецификац" in group or "тс" in name
                return (0 if is_spec else 1, name)

            downloadable = sorted(
                [d for d in documents if str(d.get("url") or "").startswith("http")],
                key=_doc_rank,
            )[: max(0, self.max_docs)]

            if self.download_docs:
                for idx, doc in enumerate(downloadable):
                    url_doc = doc.get("url")
                    try:
                        resp = page.context.request.get(str(url_doc), timeout=15000)
                        if resp.ok:
                            body = resp.body()
                            ctype = resp.headers.get("content-type") or "application/octet-stream"
                            if "text/html" in ctype and len(body) < 5000 and b"download_file" not in body[:200]:
                                doc["download_error"] = "html_instead_of_file"
                                continue
                            doc["content_type"] = ctype
                            doc["size"] = len(body)
                            fname = doc.get("name") or f"announce_{announce_id}_doc_{idx}"
                            raw_assets.append(
                                {
                                    "kind": "document",
                                    "name": str(fname),
                                    "content_type": ctype,
                                    "source_url": url_doc,
                                    "tab_name": doc.get("tab_name"),
                                    "group_name": doc.get("group_name"),
                                    "body_b64": base64.b64encode(body).decode("ascii"),
                                }
                            )
                        else:
                            doc["download_error"] = f"http_{resp.status}"
                    except Exception as exc:
                        doc["download_error"] = str(exc)

            browser.close()
        return {
            "detail_html": detail_html,
            "tabs": tabs,
            "documents": documents,
            "lots": lots,
            "contracts": contracts,
            "documentation_groups": documentation_groups,
            "raw_assets": raw_assets,
            "detail_url": url,
            "status_label": status_label,
            "overview": overview,
        }

    def _discover_items(self) -> list[dict[str, Any]]:
        if self.offline:
            html = self._load_offline_list_html()
            rows = parse_search_list(html, base_url=self.portal_base)
            filtered = [r for r in rows if self._passes_filter(r) or self.offline][: self.max_items]
            for row in filtered:
                self._cache[str(row["id"])] = row
            return filtered

        merged: dict[str, dict[str, Any]] = {}
        for search_config in self._build_search_configs():
            self._active_search_config = search_config
            url = self._search_url(search_config=search_config)
            for _ in range(self.max_pages):
                if len(merged) >= self.max_items:
                    break
                try:
                    html = self._fetch_html_playwright(url, submit_search=False, search_term=search_config.filters.get("name"))
                except Exception:
                    break
                rows = parse_search_list(html, base_url=self.portal_base)
                if not rows:
                    break
                for row in rows:
                    if self._passes_filter(row):
                        row["search_filters"] = dict(search_config.filters)
                        row["search_preset"] = search_config.preset
                        merged.setdefault(str(row["id"]), row)
                next_url = parse_search_next_page(html, base_url=self.portal_base)
                if not next_url or next_url == url:
                    break
                url = next_url
        self._active_search_config = None

        filtered = list(merged.values())[: self.max_items]
        if not filtered:
            try:
                html = self._load_offline_list_html()
                rows = parse_search_list(html, base_url=self.portal_base)
                filtered = [r for r in rows if self._passes_filter(r)][: self.max_items]
            except FileNotFoundError:
                filtered = []

        for row in filtered:
            self._cache[str(row["id"])] = row
        return filtered

    def discover_sync(self, cursor: str | None = None) -> Iterator[str]:
        del cursor
        for row in self._discover_items():
            yield str(row["id"])

    async def discover(self, cursor: str | None = None) -> AsyncIterator[str]:
        for ref in self.discover_sync(cursor):
            yield ref

    def _fetch_detail_html(self, announce_id: str) -> str:
        offline_path = self.fixture_dir / f"goszakup_announce_{announce_id}.html"
        generic_path = self.fixture_dir / "goszakup_announce_detail.html"
        if self.offline:
            if offline_path.exists():
                return offline_path.read_text(encoding="utf-8")
            if generic_path.exists():
                return generic_path.read_text(encoding="utf-8")
            raise FileNotFoundError(f"No offline detail fixture for announce {announce_id}")

        url = f"{self.portal_base}/ru/announce/index/{announce_id}"
        try:
            return self._fetch_html_playwright(url, submit_search=False)
        except Exception:
            if generic_path.exists():
                return generic_path.read_text(encoding="utf-8")
            raise

    def fetch_sync(self, ref: str) -> RawTenderPage:
        stub = self._cache.get(ref)
        if self.fetch_detail or stub is None:
            if self.offline:
                html = self._fetch_detail_html(ref)
                item = parse_announce_detail(html, announce_id=ref)
                item["goszakup_bundle"] = {
                    "detail_url": (stub or {}).get("detail_url"),
                    "tabs": [],
                    "documents": parse_documents_table(html, base_url=self.portal_base),
                    "lots": parse_lots_table(html),
                    "bidders": parse_bidders_table(html),
                    "protocols": parse_results_table(html),
                    "contracts": parse_contracts_table(html, base_url=self.portal_base),
                    "raw_assets": [
                        {
                            "kind": "detail_html",
                            "name": f"announce_{ref}.html",
                            "content_type": "text/html; charset=utf-8",
                            "source_url": (stub or {}).get("detail_url"),
                            "tab_name": "detail",
                            "body_b64": base64.b64encode(html.encode("utf-8")).decode("ascii"),
                        }
                    ],
                }
            else:
                bundle = self._fetch_bundle_playwright(ref, detail_url=(stub or {}).get("detail_url"))
                overview = bundle.get("overview") or parse_detail_overview(bundle["detail_html"], announce_id=ref)
                item = overview
                lots = bundle.get("lots") or parse_lots_table(bundle["detail_html"])
                contracts = bundle.get("contracts") or parse_contracts_table(
                    bundle["detail_html"], base_url=self.portal_base
                )
                item["goszakup_bundle"] = {
                    "detail_url": bundle["detail_url"],
                    "tabs": bundle["tabs"],
                    "documents": bundle["documents"],
                    "documentation_groups": bundle.get("documentation_groups") or [],
                    "lots": lots,
                    "bidders": parse_bidders_table(bundle["detail_html"]),
                    "protocols": parse_results_table(bundle["detail_html"]),
                    "contracts": contracts,
                    "raw_assets": bundle["raw_assets"],
                }
                if bundle.get("status_label"):
                    item["status_label"] = bundle["status_label"]
                if bundle.get("skip_reason"):
                    item["ingest_skip"] = bundle["skip_reason"]
                    item["contract_statuses_seen"] = [
                        str(c.get("status") or "") for c in contracts if c.get("status")
                    ]
            if stub:
                item = {**stub, **{k: v for k, v in item.items() if v}}
        else:
            item = dict(stub)
            item.setdefault("source", "playwright_list")

        contracts = (item.get("goszakup_bundle") or {}).get("contracts") or []
        if not item.get("ingest_skip"):
            ok, skip_reason = self._should_ingest(
                contracts=contracts,
                status_label=str(item.get("status_label") or ""),
            )
            if not ok:
                item["ingest_skip"] = skip_reason
                item["contract_statuses_seen"] = [
                    str(c.get("status") or "") for c in contracts if c.get("status")
                ]

        if self._active_search_config:
            item["search_filters"] = dict(self._active_search_config.filters)
            item["search_preset"] = self._active_search_config.preset

        payload = json.dumps(item, ensure_ascii=False).encode("utf-8")
        return RawTenderPage(
            source_code=self.source_code,
            country_code=self.country_code,
            external_id=str(item.get("number_anno") or ref),
            content_type="application/json",
            payload=payload,
        )

    async def fetch(self, ref: str) -> RawTenderPage:
        return self.fetch_sync(ref)

    def normalize(self, raw: RawTenderPage) -> NormalizedTender:
        data = json.loads(raw.payload.decode("utf-8"))
        bundle = data.get("goszakup_bundle") or {}
        title = data.get("name_ru") or data.get("name_kz") or f"Объявление {data.get('number_anno')}"
        region_blob = " ".join(
            str(data.get(k) or "") for k in ("name_ru", "org_name_ru", "org_address", "customer_name_ru")
        )
        if data.get("region_forced") == "KZ-MAN" or str((data.get("search_filters") or {}).get("kato") or "").startswith("47"):
            region_code, region_name, lat, lon = "KZ-MAN", "Мангистауская область", 43.65, 51.2
        else:
            region_code, region_name, lat, lon = map_kz_region(region_blob)
            if self.region_only in ("mangystau", "man", "kz-man") and region_code != "KZ-MAN":
                # Drop / remap only when text clearly says Mangystau; otherwise keep mapped region.
                if is_mangystau_related(region_blob):
                    region_code, region_name, lat, lon = "KZ-MAN", "Мангистауская область", 43.65, 51.2
        method = data.get("procurement_method") or "open_tender"
        amount = data.get("total_sum")
        try:
            amount_f = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            amount_f = None

        participants = data.get("participants_count")
        try:
            participants_i = int(participants) if participants is not None else None
        except (TypeError, ValueError):
            participants_i = None

        number_anno = data.get("number_anno")
        if not number_anno or not _ANNO_RE.search(str(number_anno)):
            gid = data.get("id")
            number_anno = f"{gid}-1" if gid is not None else raw.external_id

        lots = bundle.get("lots") or []
        documents = bundle.get("documents") or []
        bidders = bundle.get("bidders") or []
        protocols = bundle.get("protocols") or []
        contracts = bundle.get("contracts") or []
        tabs = bundle.get("tabs") or []
        documentation_groups = bundle.get("documentation_groups") or []
        kv = data.get("kv") or {}
        overview_tables = data.get("overview_tables") or []
        winner_name = None
        for row in protocols:
            if row.get("winner_name"):
                winner_name = row.get("winner_name")
                break
        if not winner_name:
            for row in contracts:
                if row.get("supplier"):
                    winner_name = row.get("supplier")
                    break
        if not winner_name:
            winner_name = kv.get("Победитель") or kv.get("Поставщик")

        published_at = data.get("publish_date")
        deadline_at = data.get("end_date")
        amount_total = amount_f
        if amount_total is None and lots:
            nums = [float(x["amount"]) for x in lots if x.get("amount") is not None]
            amount_total = sum(nums) if nums else None

        return NormalizedTender(
            country_code=self.country_code,
            source_code=self.source_code,
            external_id=str(number_anno),
            title=str(title),
            description=str(data.get("org_address") or ""),
            customer_name=data.get("customer_name_ru") or data.get("org_name_ru"),
            customer_external_id=kv.get("БИН (ИИН) организатора") or kv.get("БИН заказчика"),
            published_at=published_at,
            deadline_at=deadline_at,
            amount=amount_total,
            currency="KZT",
            region_code=region_code,
            region_name=region_name,
            eco_category=classify_eco_category(title),
            procurement_method=method,
            participants_count=participants_i or len(bidders) or None,
            duration_days=None,
            lat=lat,
            lon=lon,
            winner_name=winner_name,
            amendments_count=len([x for x in contracts if "соглаш" in json.dumps(x, ensure_ascii=False).lower()]),
            amendment_amount_ratio=0.0,
            extras={
                "goszakup_id": data.get("id"),
                "number_anno": data.get("number_anno"),
                "status_label": data.get("status_label"),
                "detail_url": bundle.get("detail_url") or data.get("detail_url"),
                "ingest_mode": self.mode,
                "portal_scrape": True,
                "matched_keywords": data.get("matched_keywords") or [],
                "search_filters": data.get("search_filters") or {},
                "search_preset": data.get("search_preset"),
                **({"ingest_skip": data["ingest_skip"]} if data.get("ingest_skip") else {}),
                **(
                    {"contract_statuses_seen": data["contract_statuses_seen"]}
                    if data.get("contract_statuses_seen") is not None
                    else {}
                ),
                "goszakup": {
                    "tabs": tabs,
                    "lots": lots,
                    "documents": documents,
                    "documentation_groups": documentation_groups,
                    "bidders": bidders,
                    "protocols": protocols,
                    "contracts": contracts,
                    "overview_tables": overview_tables,
                    "raw_tab_stats": {
                        "tabs_count": len(tabs),
                        "documents_count": len(documents),
                        "lots_count": len(lots),
                        "bidders_count": len(bidders),
                        "protocols_count": len(protocols),
                        "contracts_count": len(contracts),
                        "spec_docs_count": len(
                            [d for d in documents if d.get("kind") == "specification" or "спецификац" in (d.get("group_name") or "").lower()]
                        ),
                    },
                    "kv": kv,
                    "raw_assets": bundle.get("raw_assets") or [],
                },
            },
        )


def has_ows_token() -> bool:
    token = os.getenv("GOSZAKUP_TOKEN") or os.getenv("GOSZAKUP_API_TOKEN")
    if token:
        return True
    try:
        from ecotender_shared.runtime_secrets import get_active_parser_raw, get_config_value

        active = get_active_parser_raw("KZ_GOSZAKUP_OWS_V3") or get_active_parser_raw()
        if (active or {}).get("token") or get_config_value("GOSZAKUP_TOKEN"):
            return True
    except Exception:
        pass
    return False


def should_use_playwright_stub() -> bool:
    """Use Playwright when OWS token is missing and flag is enabled."""
    if has_ows_token():
        return False
    return _env_bool("GOSZAKUP_USE_PLAYWRIGHT")
