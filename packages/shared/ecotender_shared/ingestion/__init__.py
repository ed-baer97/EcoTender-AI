from ecotender_shared.ingestion.base import RawTenderPage, SourceAdapter
from ecotender_shared.ingestion.fixture_adapter import FixtureAdapter
from ecotender_shared.ingestion.goszakup_factory import resolve_goszakup_adapter
from ecotender_shared.ingestion.goszakup_kz import KazakhstanGoszakupAdapter
from ecotender_shared.ingestion.goszakup_playwright import KazakhstanGoszakupPlaywrightAdapter

__all__ = [
    "RawTenderPage",
    "SourceAdapter",
    "FixtureAdapter",
    "KazakhstanGoszakupAdapter",
    "KazakhstanGoszakupPlaywrightAdapter",
    "resolve_goszakup_adapter",
]
