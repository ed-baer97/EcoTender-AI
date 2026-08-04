"""Eco keyword filter for Caspian / environmental procurement (KZ)."""

from __future__ import annotations

ECO_KEYWORDS_RU = (
    "эколог",
    "нефт",
    "очистк",
    "рекультив",
    "берег",
    "дноуглуб",
    "монитор",
    "загрязн",
    "каспий",
    "бон",
    "шлам",
    "нефтеотход",
    "водоохран",
    "нефтезагрязн",
    "утилизац",
    "гидротехн",
    "морск",
    "порт акт",
    "курык",
    "тенгиз",
)

CASPIAN_REGION_HINTS = (
    "мангистау",
    "актау",
    "курык",
    "атырау",
    "тенгиз",
    "форт-шевченко",
    "жанаозен",
    "каспий",
)


def is_eco_related(text: str | None) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in ECO_KEYWORDS_RU)


def is_caspian_kz_related(text: str | None) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in CASPIAN_REGION_HINTS)


def classify_eco_category(text: str | None) -> str:
    t = (text or "").lower()
    if any(x in t for x in ("нефт", "бон", "разлив", "нефтезагрязн")):
        return "oil_spill_response"
    if "дноуглуб" in t:
        return "dredging"
    if "рекультив" in t:
        return "reclamation"
    if "монитор" in t or "лаборатор" in t:
        return "water_monitoring"
    if "берегоукреп" in t or "гидротехн" in t:
        return "shore_protection"
    if "очистк" in t or "утилизац" in t:
        return "coastal_cleanup"
    return "other"


def map_kz_region(text: str | None) -> tuple[str, str, float, float]:
    """Return region_code, region_name, lat, lon (approx centroids)."""
    t = (text or "").lower()
    if any(x in t for x in ("атырау", "тенгиз", "кульсары", "доссор")):
        return "KZ-ATY", "Атырауская область", 47.1, 51.9
    return "KZ-MAN", "Мангистауская область", 43.65, 51.2
