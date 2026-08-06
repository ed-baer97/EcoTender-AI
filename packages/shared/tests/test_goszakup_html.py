"""Tests for goszakup HTML parser (offline fixtures)."""

from pathlib import Path

from ecotender_shared.ingestion.goszakup_html import (
    parse_announce_detail,
    parse_bidders_table,
    parse_contracts_table,
    parse_documents_table,
    parse_lots_table,
    parse_results_table,
    parse_search_list,
)
from ecotender_shared.ingestion.goszakup_playwright import KazakhstanGoszakupPlaywrightAdapter

FIXTURES = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "html"


def test_parse_search_list_finds_eco_announces():
    html = (FIXTURES / "goszakup_search_list.html").read_text(encoding="utf-8")
    rows = parse_search_list(html)
    assert len(rows) >= 3
    ids = {r["id"] for r in rows}
    assert "910001" in ids
    assert rows[0]["number_anno"].endswith("-1")


def test_parse_announce_detail():
    html = (FIXTURES / "goszakup_announce_detail.html").read_text(encoding="utf-8")
    detail = parse_announce_detail(html, announce_id="17430846")
    assert detail["number_anno"] == "17430846-1"
    assert detail["total_sum"] == 25000.0
    assert detail["participants_count"] == 2


def test_playwright_adapter_offline_pipeline():
    adapter = KazakhstanGoszakupPlaywrightAdapter(offline=True, max_items=5, fetch_detail=True)
    refs = list(adapter.discover_sync())
    assert refs
    raw = adapter.fetch_sync(refs[0])
    norm = adapter.normalize(raw)
    assert norm.country_code == "KZ"
    assert norm.source_code == "KZ_GOSZAKUP_PLAYWRIGHT"
    assert norm.title


def test_parse_goszakup_tab_tables():
    html = (FIXTURES / "goszakup_announce_tabs.html").read_text(encoding="utf-8")
    lots = parse_lots_table(html)
    docs = parse_documents_table(html)
    bidders = parse_bidders_table(html)
    results = parse_results_table(html)
    contracts = parse_contracts_table(html)

    assert len(lots) == 2
    assert lots[0]["amount"] == 45000000.0
    assert len(docs) >= 2
    assert any(d["url"].endswith("specification.pdf") for d in docs)
    assert len(bidders) == 2
    assert bidders[0]["identifier"] == "021140002114"
    assert results[0]["winner_name"] == "КаспийЭкоСервис LLP"
    assert contracts[0]["supplier"] == "КаспийЭкоСервис LLP"
