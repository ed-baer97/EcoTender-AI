from ecotender_shared.ingestion.base import RawTenderPage, SourceAdapter
from ecotender_shared.ingestion.fixture_adapter import FixtureAdapter
from ecotender_shared.ingestion.goszakup_kz import KazakhstanGoszakupAdapter

__all__ = [
    "RawTenderPage",
    "SourceAdapter",
    "FixtureAdapter",
    "KazakhstanGoszakupAdapter",
]
