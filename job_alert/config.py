"""Load config.yaml (search settings) and companies.csv (which boards to watch)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from job_alert.models import Company

SUPPORTED_ATS = {"greenhouse", "lever", "ashby", "workday"}


@dataclass
class FilterConfig:
    include_titles: list[str] = field(default_factory=list)
    exclude_titles: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    exclude_locations: list[str] = field(default_factory=list)
    remote_ok: bool = True
    max_age_hours: int | None = 72


@dataclass
class ScoringConfig:
    enabled: bool = False
    model: str = "claude-opus-5-5"
    effort: str = "low"
    min_score: int = 60


@dataclass
class Settings:
    filters: FilterConfig
    scoring: ScoringConfig
    # Workday has no "list everything" feed, so we search each tenant by keyword.
    workday_search_terms: list[str] = field(default_factory=list)
    workday_max_pages: int = 3


def load_settings(path: str | Path) -> Settings:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return Settings(
        filters=FilterConfig(**(raw.get("filters") or {})),
        scoring=ScoringConfig(**(raw.get("scoring") or {})),
        workday_search_terms=list((raw.get("workday") or {}).get("search_terms") or []),
        workday_max_pages=int((raw.get("workday") or {}).get("max_pages", 3)),
    )


def load_companies(path: str | Path) -> list[Company]:
    """Read companies.csv. Lines starting with '#' are comments."""
    lines = [
        line
        for line in Path(path).read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    companies: list[Company] = []
    for row in csv.DictReader(lines):
        ats = (row.get("ats") or "").strip().lower()
        if ats not in SUPPORTED_ATS:
            raise ValueError(f"Unknown ats '{ats}' for {row.get('name')!r}. Use one of {sorted(SUPPORTED_ATS)}.")
        enabled = (row.get("enabled") or "true").strip().lower() not in {"false", "0", "no", "n"}
        companies.append(Company(name=row["name"].strip(), ats=ats, board=row["board"].strip(), enabled=enabled))
    return companies
