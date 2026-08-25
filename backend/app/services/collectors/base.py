"""Trend collector abstraction.

Every trend source (Google Trends, YouTube, ...) implements `TrendCollector`
and is isolated in its own module, per the Project Constitution's rule that
trend sources must not be mixed throughout the application. The scoring
system (app/services/scoring.py) is intentionally kept separate from
collectors: a collector's only job is to fetch and normalize raw items,
never to score them.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CollectedItem:
    """A single, normalized trend candidate returned by a collector."""

    title: str
    source: str
    url: str
    published_at: datetime | None
    metrics: dict = field(default_factory=dict)
    # Optional language / content signals (YouTube). Description is never
    # used alone for English acceptance — see language.classify_trend_language.
    description: str | None = None
    default_language: str | None = None
    default_audio_language: str | None = None


class CollectorError(Exception):
    """Raised when a collector fails to fetch data (network, API error, ...)."""


class CollectorNotConfiguredError(CollectorError):
    """Raised when a collector is missing required configuration (e.g. an API key).

    This is the sanctioned fallback for external services we can't reliably
    integrate without credentials: fail clearly and specifically, never
    fabricate data pretending it came from a real source.
    """


class TrendCollector(ABC):
    source_name: str

    @abstractmethod
    async def collect(
        self,
        query: str,
        limit: int = 10,
        *,
        exclude_urls: set[str] | None = None,
    ) -> list[CollectedItem]:
        """Fetch up to `limit` items relevant to `query`.

        Must raise CollectorError (or CollectorNotConfiguredError) on failure
        rather than returning fabricated or partial-silent results.
        `exclude_urls` lets callers ask for fresher results than ones already stored.
        """
        raise NotImplementedError
