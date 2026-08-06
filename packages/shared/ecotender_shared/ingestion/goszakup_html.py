"""Parse goszakup.gov.kz public HTML (search list + announce detail)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

PORTAL_BASE = "https://goszakup.gov.kz"
_ANNO_RE = re.compile(r"(\d{5,})-(\d+)")
_ANNO_ID_RE = re.compile(r"/announce/index/(\d+)")
_AMOUNT_RE = re.compile(r"[\d\s]+(?:[.,]\d+)?")
_METHOD_MAP = {
    "открытый конкурс": "open_tender",
    "запрос ценовых предложений": "request_price",
    "из одного источника": "single_source",
    "аукцион": "auction",
}


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _parse_amount(text: str | None) -> float | None:
    if not text:
        return None
    raw = text.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    m = re.search(r"[\d.]+", raw)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _map_method(label: str | None) -> str:
    t = (label or "").lower()
    for key, val in _METHOD_MAP.items():
        if key in t:
            return val
    return "open_tender"


def _split_title_organizer(cell_text: str) -> tuple[str, str | None]:
    text = _clean(cell_text)
    if "Организатор:" in text:
        title, _, org = text.partition("Организатор:")
        return _clean(title), _clean(org) or None
    return text, None


def parse_search_list(html: str, *, base_url: str = PORTAL_BASE) -> list[dict[str, Any]]:
    """Extract announce stubs from /ru/search/announce HTML."""
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    items: list[dict[str, Any]] = []

    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        link = row.select_one("a[href*='/announce/index/']")
        if link is None:
            continue
        href = link.get("href") or ""
        id_m = _ANNO_ID_RE.search(href)
        if not id_m:
            continue
        announce_id = id_m.group(1)
        if announce_id in seen:
            continue
        seen.add(announce_id)

        number_anno = None
        head_text = _clean(link.get_text(" ", strip=True))
        num_m = _ANNO_RE.search(head_text)
        if num_m:
            number_anno = f"{num_m.group(1)}-{num_m.group(2)}"
        elif announce_id.isdigit():
            number_anno = f"{announce_id}-1"
        else:
            number_anno = announce_id

        title_cell = cells[1] if len(cells) > 1 else link
        title, organizer = _split_title_organizer(title_cell.get_text(" ", strip=True))
        method = _map_method(cells[2].get_text(" ", strip=True) if len(cells) > 2 else "")
        amount = _parse_amount(cells[5].get_text(" ", strip=True) if len(cells) > 5 else None)
        status = _clean(cells[6].get_text(" ", strip=True) if len(cells) > 6 else "")

        items.append(
            {
                "id": announce_id,
                "number_anno": number_anno,
                "name_ru": title,
                "org_name_ru": organizer,
                "ref_trade_methods_id": None,
                "procurement_method": method,
                "total_sum": amount,
                "ref_buy_status_id": None,
                "status_label": status,
                "detail_url": urljoin(base_url, href),
                "publish_date": None,
                "start_date": _clean(cells[3].get_text(" ", strip=True) if len(cells) > 3 else ""),
                "end_date": _clean(cells[4].get_text(" ", strip=True) if len(cells) > 4 else ""),
            }
        )

    if items:
        return items

    # Fallback: any announce links on page (sparse markup)
    for link in soup.select("a[href*='/announce/index/']"):
        href = link.get("href") or ""
        id_m = _ANNO_ID_RE.search(href)
        if not id_m:
            continue
        announce_id = id_m.group(1)
        if announce_id in seen:
            continue
        seen.add(announce_id)
        text = _clean(link.get_text(" ", strip=True))
        num_m = _ANNO_RE.search(text)
        number_anno = f"{num_m.group(1)}-{num_m.group(2)}" if num_m else (
            f"{announce_id}-1" if announce_id.isdigit() else announce_id
        )
        items.append(
            {
                "id": announce_id,
                "number_anno": number_anno,
                "name_ru": text,
                "org_name_ru": None,
                "procurement_method": "open_tender",
                "total_sum": None,
                "detail_url": urljoin(base_url, href),
            }
        )
    return items


def parse_search_next_page(html: str, *, base_url: str = PORTAL_BASE) -> str | None:
    """Return absolute URL for the next search results page, if any."""
    soup = BeautifulSoup(html, "lxml")
    for link in soup.select("a[href*='search/announce']"):
        text = _clean(link.get_text(" ", strip=True)).lower()
        href = link.get("href") or ""
        if not href or href.startswith("#"):
            continue
        if any(x in text for x in ("след", "next", "»", "›")) or "page=next" in href:
            return urljoin(base_url, href)
    for link in soup.select("ul.pagination a[href], nav.pagination a[href], .pagination a[href]"):
        text = _clean(link.get_text(" ", strip=True))
        href = link.get("href") or ""
        if text.isdigit() and int(text) > 1:
            return urljoin(base_url, href)
    return None


def _table_rows(table: BeautifulSoup) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.select("tr"):
        cells = [_clean(c.get_text(" ", strip=True)) for c in row.find_all(["th", "td"])]
        if any(cells):
            rows.append(cells)
    return rows


def parse_detail_overview(html: str, *, announce_id: str) -> dict[str, Any]:
    """Detail page parsed into flat overview plus raw kv."""
    soup = BeautifulSoup(html, "lxml")
    kv = _table_kv(soup)
    detail = parse_announce_detail(html, announce_id=announce_id)
    detail["kv"] = kv
    detail["overview_tables"] = parse_overview_tables(html)
    return detail


def parse_overview_tables(html: str) -> list[dict[str, Any]]:
    """Extract labeled th/td key-value tables (Общие сведения, Информация об организаторе, …)."""
    soup = BeautifulSoup(html, "lxml")
    sections: list[dict[str, Any]] = []
    for table in soup.select("table"):
        rows_kv: list[dict[str, str]] = []
        for row in table.select("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            # Skip wide data grids (lots/docs) — keep 2-column label/value tables.
            if len(cells) > 3:
                rows_kv = []
                break
            key = _clean(cells[0].get_text(" ", strip=True))
            val = _clean(cells[1].get_text(" ", strip=True))
            if key and val and key.lower() != val.lower():
                rows_kv.append({"label": key, "value": val})
        if len(rows_kv) >= 2:
            heading = None
            prev = table.find_previous(["h3", "h4", "h5", "legend", "strong"])
            if prev:
                heading = _clean(prev.get_text(" ", strip=True)) or None
            sections.append({"title": heading, "rows": rows_kv})
    return sections


_ACTION_MODAL_RE = re.compile(r"actionModalShowFiles\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", re.I)


def parse_documentation_groups(html: str) -> list[dict[str, Any]]:
    """Parse Документация tab rows with actionModalShowFiles(announce, group)."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in soup.select("table tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 1:
            continue
        onclick = ""
        for el in row.select("[onclick], button, a"):
            onclick = el.get("onclick") or ""
            if "actionModalShowFiles" in onclick:
                break
        m = _ACTION_MODAL_RE.search(onclick)
        if not m:
            # Also scan raw row HTML for the call.
            m = _ACTION_MODAL_RE.search(str(row))
        if not m:
            continue
        announce_id, group_id = m.group(1), m.group(2)
        key = f"{announce_id}:{group_id}"
        if key in seen:
            continue
        seen.add(key)
        name = _clean(cells[0].get_text(" ", strip=True))
        flag = _clean(cells[1].get_text(" ", strip=True)) if len(cells) > 1 else ""
        out.append(
            {
                "name": name or f"group_{group_id}",
                "group_id": group_id,
                "announce_id": announce_id,
                "required_flag": flag,
                "kind": "documentation_group",
            }
        )
    return out


def parse_modal_files(html: str, *, base_url: str = PORTAL_BASE) -> list[dict[str, Any]]:
    """Parse #ModalShowFilesBody / actionAjaxModalShowFiles response table.

    A single modal group (e.g. Техническая спецификация) often contains many file rows.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _is_file_href(href: str) -> bool:
        low = href.lower()
        if "signature" in low and "download_file" not in low:
            return False
        return any(x in low for x in ("download_file", ".pdf", ".doc", ".docx", ".xls", ".xlsx", "/files/"))

    for table in soup.select("table"):
        rows = table.select("tr")
        if len(rows) < 2:
            continue
        headers = [_clean(c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"])]
        header_blob = " ".join(headers).lower()
        has_download = any(
            a.get("href") and _is_file_href(a.get("href") or "") for a in table.select("a[href]")
        )
        if "документ" not in header_blob and not has_download:
            continue
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            vals = [_clean(c.get_text(" ", strip=True)) for c in cells]
            item = {headers[i] if i < len(headers) else f"col_{i}": vals[i] for i in range(len(vals))}
            lot_number = next((v for k, v in item.items() if "лот" in k.lower()), vals[0] if vals else None)
            author = next((v for k, v in item.items() if "автор" in k.lower()), None)
            organization = next((v for k, v in item.items() if "организац" in k.lower()), None)
            created_at = next((v for k, v in item.items() if "дата" in k.lower()), None)

            # Prefer file links in the «Документ» column; fall back to all row file links.
            doc_cell = None
            for i, h in enumerate(headers):
                if "документ" in h.lower() and i < len(cells):
                    doc_cell = cells[i]
                    break
            link_nodes = (doc_cell.select("a[href]") if doc_cell is not None else []) or row.select("a[href]")
            file_links = []
            for link in link_nodes:
                href = link.get("href") or ""
                if not _is_file_href(href):
                    continue
                abs_href = urljoin(base_url, href)
                if abs_href in seen:
                    continue
                seen.add(abs_href)
                file_links.append((_clean(link.get_text(" ", strip=True)) or abs_href, abs_href))

            for name, abs_href in file_links:
                low_name = name.lower()
                out.append(
                    {
                        "name": name,
                        "url": abs_href,
                        "lot_number": lot_number,
                        "author": author,
                        "organization": organization,
                        "created_at": created_at,
                        "row": vals,
                        "kind": "specification"
                        if any(x in low_name for x in ("тс", "спецификац", "techspec"))
                        or any(x in abs_href.lower() for x in (".docx", ".doc", ".pdf", "download_file"))
                        else "document",
                    }
                )
    return out


def parse_documents_table(html: str, *, base_url: str = PORTAL_BASE) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for table in soup.select("table"):
        rows = table.select("tr")
        if len(rows) < 1:
            continue
        for row in rows:
            cells = row.find_all(["td", "th"])
            links = row.select("a[href]")
            if not links:
                continue
            href = links[0].get("href") or ""
            abs_href = urljoin(base_url, href)
            if abs_href in seen:
                continue
            # Skip signature-only links; modal file parser handles those separately.
            if "signature" in abs_href.lower() and "download_file" not in abs_href.lower():
                continue
            seen.add(abs_href)
            cell_texts = [_clean(c.get_text(" ", strip=True)) for c in cells]
            out.append(
                {
                    "name": _clean(links[0].get_text(" ", strip=True)) or (cell_texts[0] if cell_texts else abs_href),
                    "url": abs_href,
                    "row": cell_texts,
                    "kind": "document",
                }
            )
    if out:
        return out
    for link in soup.select("a[href]"):
        href = link.get("href") or ""
        low = href.lower()
        if not any(x in low for x in (".pdf", ".doc", ".docx", ".xls", ".xlsx", "download_file", "download", "file")):
            continue
        abs_href = urljoin(base_url, href)
        if abs_href in seen:
            continue
        seen.add(abs_href)
        out.append(
            {
                "name": _clean(link.get_text(" ", strip=True)) or abs_href,
                "url": abs_href,
                "row": [],
                "kind": "document",
            }
        )
    return out


def parse_lots_table(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    for table in soup.select("table"):
        rows = _table_rows(table)
        if len(rows) < 2:
            continue
        header_blob = " ".join(rows[0]).lower()
        if "лот" not in header_blob and "наимен" not in header_blob:
            continue
        if not any(k in header_blob for k in ("наимен", "сумма", "кол-во", "заказчик", "цена")):
            continue
        headers = rows[0]
        for row in rows[1:]:
            if len(row) < 2:
                continue
            item = {headers[i] if i < len(headers) else f"col_{i}": row[i] for i in range(len(row))}
            name = next(
                (v for k, v in item.items() if "наимен" in k.lower()),
                row[3] if len(row) > 3 else (row[1] if len(row) > 1 else row[0]),
            )
            amount = next(
                (
                    _parse_amount(v)
                    for k, v in item.items()
                    if any(x in k.lower() for x in ("планов", "сумма", "цена"))
                    and _parse_amount(v) is not None
                ),
                None,
            )
            lot_no = next((v for k, v in item.items() if "номер лота" in k.lower() or k.lower() == "№ лота"), None)
            out.append({"name": name, "amount": amount, "lot_number": lot_no, "raw": item})
    return out


def parse_bidders_table(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    for table in soup.select("table"):
        rows = _table_rows(table)
        if len(rows) < 2:
            continue
        header_blob = " ".join(rows[0]).lower()
        if not any(k in header_blob for k in ("участник", "заявк", "бин", "иин")):
            continue
        headers = rows[0]
        for row in rows[1:]:
            if len(row) < 1:
                continue
            item = {headers[i] if i < len(headers) else f"col_{i}": row[i] for i in range(len(row))}
            out.append(
                {
                    "name": next((v for k, v in item.items() if any(x in k.lower() for x in ("участ", "поставщ", "наимен"))), row[0]),
                    "identifier": next((v for k, v in item.items() if any(x in k.lower() for x in ("бин", "иин"))), None),
                    "status": next((v for k, v in item.items() if "стат" in k.lower()), None),
                    "raw": item,
                }
            )
    return out


def parse_results_table(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    for table in soup.select("table"):
        rows = _table_rows(table)
        if len(rows) < 2:
            continue
        header_blob = " ".join(rows[0]).lower()
        if not any(k in header_blob for k in ("побед", "итог", "результ", "заявк")):
            continue
        headers = rows[0]
        for row in rows[1:]:
            item = {headers[i] if i < len(headers) else f"col_{i}": row[i] for i in range(len(row))}
            out.append(
                {
                    "winner_name": next((v for k, v in item.items() if "побед" in k.lower()), None),
                    "status": next((v for k, v in item.items() if "стат" in k.lower()), None),
                    "raw": item,
                }
            )
    return out


def parse_contracts_table(html: str, *, base_url: str = PORTAL_BASE) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    for table in soup.select("table"):
        rows = table.select("tr")
        if len(rows) < 2:
            continue
        header_blob = " ".join(_clean(x.get_text(" ", strip=True)) for x in rows[0].find_all(["th", "td"])).lower()
        if not any(k in header_blob for k in ("договор", "соглашен")):
            continue
        headers = [_clean(x.get_text(" ", strip=True)) for x in rows[0].find_all(["th", "td"])]
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            vals = [_clean(c.get_text(" ", strip=True)) for c in cells]
            links = [urljoin(base_url, a.get("href") or "") for a in row.select("a[href]")]
            item = {headers[i] if i < len(headers) else f"col_{i}": vals[i] for i in range(len(vals))}
            out.append(
                {
                    "name": next((v for k, v in item.items() if "договор" in k.lower()), vals[0] if vals else None),
                    "supplier": next((v for k, v in item.items() if "поставщик" in k.lower()), vals[1] if len(vals) > 1 else None),
                    "amount": next((_parse_amount(v) for k, v in item.items() if "сум" in k.lower()), None),
                    "status": next((v for k, v in item.items() if "стат" in k.lower()), None),
                    "links": links,
                    "raw": item,
                }
            )
    return out


def _table_kv(soup: BeautifulSoup) -> dict[str, str]:
    out: dict[str, str] = {}
    for table in soup.select("table"):
        for row in table.select("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                key = _clean(cells[0].get_text(" ", strip=True))
                val = _clean(cells[1].get_text(" ", strip=True))
                if key:
                    out[key] = val
    return out


def parse_announce_detail(html: str, *, announce_id: str) -> dict[str, Any]:
    """Parse /ru/announce/index/{id} HTML into OWS-like dict."""
    soup = BeautifulSoup(html, "lxml")
    kv = _table_kv(soup)

    title = kv.get("Наименование объявления") or kv.get("Наименование")
    number_anno = kv.get("Номер объявления")
    if not number_anno:
        head = soup.find(string=re.compile(r"Просмотр объявления"))
        if head:
            m = _ANNO_RE.search(head)
            if m:
                number_anno = f"{m.group(1)}-{m.group(2)}"

    organizer = kv.get("Организатор") or kv.get("Организатор закупки")
    method_label = kv.get("Способ проведения закупки") or kv.get("Способ закупки")
    amount = _parse_amount(kv.get("Сумма закупки"))

    return {
        "id": int(announce_id) if announce_id.isdigit() else announce_id,
        "number_anno": number_anno or f"{announce_id}-1",
        "name_ru": title,
        "name_kz": title,
        "org_name_ru": organizer,
        "customer_name_ru": organizer,
        "ref_trade_methods_id": None,
        "procurement_method": _map_method(method_label),
        "total_sum": amount,
        "publish_date": kv.get("Дата публикации объявления"),
        "start_date": kv.get("Срок начала приема заявок"),
        "end_date": kv.get("Срок окончания приема заявок"),
        "ref_buy_status_id": None,
        "status_label": kv.get("Статус объявления"),
        "count_lots": kv.get("Кол-во лотов в объявлении"),
        "org_address": kv.get("Юр. адрес организатора"),
        "participants_count": _parse_participants(soup),
        "source": "playwright_html",
    }


def _parse_participants(soup: BeautifulSoup) -> int | None:
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Кол-во поданных заявок:\s*(\d+)", text)
    if m:
        return int(m.group(1))
    return None
