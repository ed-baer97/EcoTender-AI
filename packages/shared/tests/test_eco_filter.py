"""Unit tests for eco / region filters."""

from ecotender_shared.ingestion.eco_filter import (
    is_mangystau_related,
    map_kz_region,
)


def test_map_kz_region_does_not_default_to_mangystau():
    code, name, lat, lon = map_kz_region("г. Алматы, ул. Площадь Республики")
    assert code == "KZ-ALA"
    assert lat is not None

    code, name, lat, lon = map_kz_region("Карагандинская область, г.Караганда")
    assert code == "KZ-KAR"

    code, name, lat, lon = map_kz_region("")
    assert code == "KZ-UNK"
    assert lat is None


def test_map_kz_region_mangystau():
    code, name, lat, lon = map_kz_region('ГУ "Управление природных ресурсов Мангистауской области"')
    assert code == "KZ-MAN"
    assert "Мангистау" in name
    assert lat == 43.65


def test_is_mangystau_related():
    assert is_mangystau_related("Департамент полиции Мангистауской области")
    assert is_mangystau_related("порт Актау")
    assert not is_mangystau_related("Управление экологии города Алматы")
    assert not is_mangystau_related("Павлодарская область")
