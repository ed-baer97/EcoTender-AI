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
    "бонов",
    "бонн",
    "бон-заград",
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

MANGYSTAU_HINTS = (
    "мангистау",
    "мангыстау",
    "маңғыстау",
    "актау",
    "ақтау",
    "курык",
    "құрық",
    "жанаозен",
    "жаңаөзен",
    "форт-шевченко",
    "тупкараган",
    "түпқараған",
    "бейнеу",
    "мунайлы",
    "мұнайлы",
    "каракия",
    "қарақия",
    "мангышлак",
    "порт актау",
)

CASPIAN_REGION_HINTS = MANGYSTAU_HINTS + (
    "атырау",
    "тенгиз",
    "каспий",
    "кульсары",
    "доссор",
)

# Longer / more specific patterns first to avoid false positives.
_REGION_RULES: tuple[tuple[tuple[str, ...], str, str, float, float], ...] = (
    (("мангистау", "мангыстау", "маңғыстау", "актау", "ақтау", "курык", "жанаозен", "форт-шевченко", "тупкараган", "бейнеу", "мунайлы", "каракия", "мангышлак"), "KZ-MAN", "Мангистауская область", 43.65, 51.2),
    (("атырау", "тенгиз", "кульсары", "доссор"), "KZ-ATY", "Атырауская область", 47.1, 51.9),
    (("алматы", "алматин", "медеу", "бостандык", "ауэзов", "жетысуск", "алатауск", "наурызбай"), "KZ-ALA", "г. Алматы / Алматинская область", 43.24, 76.95),
    (("астана", "нур-султан", "акмолин"), "KZ-AST", "г. Астана / Акмолинская область", 51.17, 71.45),
    (("шымкент", "туркестан"), "KZ-SHY", "г. Шымкент / Туркестанская область", 42.34, 69.59),
    (("караганд", "қарағанд"), "KZ-KAR", "Карагандинская область", 49.8, 73.1),
    (("павлодар",), "KZ-PAV", "Павлодарская область", 52.29, 76.97),
    (("костанай", "қостанай"), "KZ-KOS", "Костанайская область", 53.21, 63.62),
    (("восточно-казахстан", "вко", "усть-каменогорск", "өскемен"), "KZ-VKO", "Восточно-Казахстанская область", 49.95, 82.61),
    (("западно-казахстан", "уральск", "орал"), "KZ-ZKO", "Западно-Казахстанская область", 51.23, 51.37),
    (("актобе", "актюбин"), "KZ-AKT", "Актюбинская область", 50.28, 57.21),
    (("жамбыл", "тараз"), "KZ-ZHA", "Жамбылская область", 42.9, 71.37),
    (("кызылорда", "қызылорда"), "KZ-KZY", "Кызылординская область", 44.85, 65.51),
    (("северо-казахстан", "петропавловск"), "KZ-SKO", "Северо-Казахстанская область", 54.87, 69.15),
    (("абайская", "области абай", "область абай", "г. семей", "г.семей"), "KZ-ABA", "область Абай", 50.41, 80.25),
    (("жетісу", "жетису", "талдыкорган"), "KZ-ZET", "область Жетісу", 45.02, 78.37),
    (("улытау", "ұлытау", "жезказган"), "KZ-ULY", "область Улытау", 47.8, 67.7),
)


def is_eco_related(text: str | None) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in ECO_KEYWORDS_RU)


def is_mangystau_related(text: str | None) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in MANGYSTAU_HINTS)


def is_caspian_kz_related(text: str | None) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in CASPIAN_REGION_HINTS)


def classify_eco_category(text: str | None) -> str:
    t = (text or "").lower()
    if any(x in t for x in ("нефт", "бонов", "бонн", "бон-заград", "разлив", "нефтезагрязн")):
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


def map_kz_region(text: str | None) -> tuple[str, str, float | None, float | None]:
    """Return region_code, region_name, lat, lon (approx centroids).

    Unmatched text returns KZ-UNK with null coordinates — never invent Mangystau.
    """
    t = (text or "").lower()
    if not t.strip():
        return "KZ-UNK", "Регион не определён", None, None
    for hints, code, name, lat, lon in _REGION_RULES:
        if any(h in t for h in hints):
            return code, name, lat, lon
    return "KZ-UNK", "Регион не определён", None, None
