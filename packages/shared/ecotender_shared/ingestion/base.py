from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from hashlib import sha256

from pydantic import BaseModel, Field

from ecotender_shared.schemas import NormalizedTender


class RawTenderPage(BaseModel):
    source_code: str
    country_code: str
    external_id: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_type: str
    payload: bytes
    checksum: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.checksum:
            self.checksum = sha256(self.payload).hexdigest()


class SourceAdapter(ABC):
    """Multi-country extension point. Add AZ/RU/TM/IR without touching tender-service."""

    source_code: str
    country_code: str

    @abstractmethod
    async def discover(self, cursor: str | None = None) -> AsyncIterator[str]:
        """Yield external refs (ids or URLs)."""
        raise NotImplementedError
        yield  # pragma: no cover — makes this an async generator type

    @abstractmethod
    async def fetch(self, ref: str) -> RawTenderPage:
        ...

    @abstractmethod
    def normalize(self, raw: RawTenderPage) -> NormalizedTender:
        ...
