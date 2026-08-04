from enum import Enum


class RiskBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UserRole(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    AUDITOR = "auditor"
    ADMIN = "admin"


class EcoCategory(str, Enum):
    COASTAL_CLEANUP = "coastal_cleanup"
    OIL_SPILL_RESPONSE = "oil_spill_response"
    DREDGING = "dredging"
    SHORE_PROTECTION = "shore_protection"
    WATER_MONITORING = "water_monitoring"
    RECLAMATION = "reclamation"
    WASTE_TREATMENT = "waste_treatment"
    BIODIVERSITY = "biodiversity"
    OTHER = "other"


class AnomalyType(str, Enum):
    PRICE_OUTLIER = "PRICE_OUTLIER"
    SINGLE_BIDDER = "SINGLE_BIDDER"
    REPEAT_WINNER = "REPEAT_WINNER"
    AMENDMENT_SPIKE = "AMENDMENT_SPIKE"
    GEO_MISMATCH = "GEO_MISMATCH"
    COAST_ECO_CONFLICT = "COAST_ECO_CONFLICT"
    SHORT_WINDOW = "SHORT_WINDOW"


def score_to_band(score: float) -> RiskBand:
    if score >= 80:
        return RiskBand.CRITICAL
    if score >= 60:
        return RiskBand.HIGH
    if score >= 30:
        return RiskBand.MEDIUM
    return RiskBand.LOW
