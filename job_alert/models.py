"""Core data types shared by fetchers, filters, the store and notifiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Company:
    """One row of companies.csv."""

    name: str
    ats: str  # greenhouse | lever | ashby | workday
    board: str  # slug (greenhouse/lever/ashby) or careers-site URL (workday)
    enabled: bool = True


@dataclass
class Job:
    """A normalized job posting, whatever board it came from."""

    source: str
    company: str
    external_id: str
    title: str
    location: str
    url: str
    posted_at: datetime | None = None
    remote: bool = False
    description: str = ""
    # Filled in later by the scorer (optional).
    score: int | None = None
    score_reasons: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable unique id used for de-duplication across runs."""
        return f"{self.source}:{self.company}:{self.external_id}".lower()
