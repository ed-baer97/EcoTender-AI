"""Tests for goszakup HTML parser (offline fixtures)."""

from pathlib import Path

from ecotender_shared.ingestion.goszakup_html import (
    parse_announce_detail,
    parse_bidders_table,
    parse_contracts_table,
    parse_documentation_groups,
    parse_documents_table,
    parse_lots_table,
    parse_modal_files,
    parse_overview_tables,
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


def test_search_config_status_multi_query():
    from ecotender_shared.ingestion.goszakup_playwright import SearchConfig

    q = SearchConfig(
        filters={"kato": "470000000", "status": "350", "signs": "is_not_active", "amount_from": "1000000"},
        matched_keywords=[],
    ).to_query()
    assert "filter%5Bstatus%5D%5B%5D=350" in q or "filter[status][]=350" in q.replace("%5B", "[").replace("%5D", "]")
    assert "is_not_active" in q
    assert "470000000" in q


def test_contract_status_filter_accepts_executed():
    adapter = KazakhstanGoszakupPlaywrightAdapter(offline=True, max_items=1, fetch_detail=False)
    adapter.require_contract_status = True
    adapter.contract_statuses = ["действует", "исполнен"]
    assert adapter._contracts_match_required_status(
        [{"status": "Передан.Исполнен", "supplier": "X"}]
    )
    assert adapter._contracts_match_required_status([{"status": "Действует"}])
    assert not adapter._contracts_match_required_status([{"status": "Не заключен"}])
    assert adapter._contracts_match_required_status([])  # empty allowed unless REQUIRE_CONTRACT_ROWS


def test_should_ingest_allows_completed_without_contracts():
    adapter = KazakhstanGoszakupPlaywrightAdapter(offline=True, max_items=1, fetch_detail=False)
    adapter.require_contract_status = True
    adapter.require_contract_rows = False
    adapter.contract_statuses = ["действует", "исполнен"]
    ok, reason = adapter._should_ingest(contracts=[], status_label="Завершено")
    assert ok and reason is None
    ok, reason = adapter._should_ingest(contracts=[{"status": "Не заключен"}], status_label="Завершено")
    assert not ok
    assert reason == "contract_status_not_active_or_executed"


def test_open_announce_status_rejected():
    adapter = KazakhstanGoszakupPlaywrightAdapter(offline=True, max_items=1, fetch_detail=False)
    adapter.announce_status = "350"
    assert not adapter._passes_filter(
        {
            "name_ru": "Очистка Мангистау",
            "org_name_ru": "Акимат Мангистау",
            "status_label": "Опубликовано (прием заявок)",
            "total_sum": 5_000_000,
        }
    )
    assert adapter._passes_filter(
        {
            "name_ru": "Очистка Мангистау",
            "org_name_ru": "Акимат Мангистау",
            "status_label": "Завершено",
            "total_sum": 5_000_000,
            "region_forced": "KZ-MAN",
        }
    )


def test_parse_overview_and_modal_specification():
    detail = (FIXTURES / "goszakup_announce_detail.html").read_text(encoding="utf-8")
    sections = parse_overview_tables(detail)
    assert sections
    labels = {r["label"] for s in sections for r in s["rows"]}
    assert "Организатор" in labels or "Юр. адрес организатора" in labels

    modal = (FIXTURES / "goszakup_modal_files.html").read_text(encoding="utf-8")
    groups = parse_documentation_groups(modal)
    assert any(g["group_id"] == "102" and "спецификац" in g["name"].lower() for g in groups)
    files = parse_modal_files(modal)
    assert len(files) >= 4
    names = [f["name"] for f in files]
    assert any("Тупкараган су" in n for n in names)
    assert any("Смета" in n for n in names)
    assert any("Приложение к ТС" in n for n in names)
    assert all("download_file" in f["url"] for f in files)
    assert all("signature" not in f["url"] for f in files)


