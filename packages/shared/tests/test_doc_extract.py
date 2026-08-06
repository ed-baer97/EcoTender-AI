"""Tests for document text extraction helpers."""

from __future__ import annotations

from ecotender_shared.doc_extract import (
    build_extract_record,
    extract_text_from_bytes,
    merge_doc_extracts,
    rank_doc_extracts,
)


def test_extract_plain_text():
    excerpt, err = extract_text_from_bytes(
        "Спецификация: очистка территории Мангистау".encode("utf-8"),
        content_type="text/plain",
        filename="spec.txt",
    )
    assert err is None
    assert "Мангистау" in excerpt


def test_merge_keeps_existing_excerpt():
    existing = [
        build_extract_record(
            name="a.pdf",
            kind="specification",
            sha256="abc",
            excerpt="old text",
        )
    ]
    new = [
        build_extract_record(
            name="a.pdf",
            kind="specification",
            sha256="abc",
            excerpt="new text",
        )
    ]
    merged = merge_doc_extracts(existing, new)
    assert len(merged) == 1
    assert merged[0]["excerpt"] == "old text"


def test_rank_prefers_specification():
    items = [
        build_extract_record(name="other.pdf", kind="document", sha256="1", excerpt="x"),
        build_extract_record(name="tz.pdf", kind="specification", sha256="2", excerpt="y"),
    ]
    ranked = rank_doc_extracts(items, limit=2)
    assert ranked[0]["kind"] == "specification"
