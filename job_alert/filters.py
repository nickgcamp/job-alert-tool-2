"""Decide which postings are worth an alert: title, location and freshness."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from job_alert.config import FilterConfig
from job_alert.models import Job


@lru_cache(maxsize=512)
def _phrase(term: str) -> re.Pattern:
    """Whole-word, case-insensitive match that also works for terms like 'FP&A' or 'Sr.'."""
    words = [re.escape(w) for w in term.lower().split()]
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-/]+".join(words) + r"(?![a-z0-9])")


def matches_any(text: str, terms: list[str]) -> bool:
    low = (text or "").lower()
    return any(_phrase(t).search(low) for t in terms if t.strip())


def title_ok(job: Job, cfg: FilterConfig) -> bool:
    if cfg.include_titles and not matches_any(job.title, cfg.include_titles):
        return False
    return not matches_any(job.title, cfg.exclude_titles)


def location_ok(job: Job, cfg: FilterConfig) -> bool:
    if matches_any(job.location, cfg.exclude_locations):
        return False
    if cfg.remote_ok and job.remote:
        return True
    if not cfg.locations:
        return True
    return matches_any(job.location, cfg.locations)


def fresh_enough(job: Job, cfg: FilterConfig, now: datetime | None = None) -> bool:
    """Postings with no date pass; the 'seen before' check still stops repeats."""
    if cfg.max_age_hours is None or job.posted_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    return now - job.posted_at <= timedelta(hours=cfg.max_age_hours)


def why_rejected(job: Job, cfg: FilterConfig, now: datetime | None = None) -> str | None:
    """Return None if the job passes, else a short reason (handy for --verbose runs)."""
    if not title_ok(job, cfg):
        return "title"
    if not location_ok(job, cfg):
        return "location"
    if not fresh_enough(job, cfg, now):
        return "too old"
    return None


def apply_filters(jobs: list[Job], cfg: FilterConfig, now: datetime | None = None) -> list[Job]:
    return [j for j in jobs if why_rejected(j, cfg, now) is None]
