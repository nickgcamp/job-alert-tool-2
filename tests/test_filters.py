from datetime import datetime, timedelta, timezone

import pytest

from job_alert import filters
from job_alert.config import FilterConfig
from job_alert.models import Job

NOW = datetime(2026, 11, 17, 23, 0, tzinfo=timezone.utc)


def job(title="Financial Analyst", location="Minneapolis, MN", remote=False, age_hours=1):
    return Job(
        source="test", company="Acme", external_id=title, title=title, location=location, url="https://example.com",
        posted_at=NOW - timedelta(hours=age_hours) if age_hours is not None else None, remote=remote,
    )


@pytest.mark.parametrize(
    "title",
    ["Senior Financial Analyst", "FP&A Analyst", "Sr. Financial Analyst - FP&A", "Financial Planning & Analysis Analyst",
     "Analyst, FP & A", "Financial-Analyst II", "Strategic Finance Associate"],
)
def test_target_titles_match(settings, title):
    assert filters.title_ok(job(title), settings.filters)


@pytest.mark.parametrize(
    "title",
    ["Software Engineer", "FP&A Intern", "Director, FP&A", "VP of Financial Planning", "Head of FP&A",
     "Financial Analyst Internship (Summer 2027)", "Analyst Relations Manager"],
)
def test_other_titles_rejected(settings, title):
    assert not filters.title_ok(job(title), settings.filters)


def test_whole_words_only():
    cfg = FilterConfig(include_titles=["fp&a"], exclude_titles=["vp"])
    assert filters.title_ok(job("FP&A Lead"), cfg)
    # 'vp' must not knock out titles that merely contain the letters
    assert filters.title_ok(job("FP&A Analyst, Supply Chain (VPN team)"), cfg)
    assert not filters.title_ok(job("VP, FP&A"), cfg)


@pytest.mark.parametrize("location", ["Minneapolis, MN", "Eden Prairie, Minnesota", "St. Paul, MN", "Hybrid - Twin Cities"])
def test_local_locations_pass(settings, location):
    assert filters.location_ok(job(location=location), settings.filters)


def test_far_locations_rejected_unless_remote(settings):
    assert not filters.location_ok(job(location="Austin, TX"), settings.filters)
    assert filters.location_ok(job(location="Austin, TX", remote=True), settings.filters)


def test_excluded_locations_beat_remote(settings):
    assert not filters.location_ok(job(location="Remote - Canada", remote=True), settings.filters)


def test_remote_not_ok():
    cfg = FilterConfig(locations=["minneapolis"], remote_ok=False)
    assert not filters.location_ok(job(location="Remote - US", remote=True), cfg)


def test_freshness(settings):
    assert filters.fresh_enough(job(age_hours=2), settings.filters, NOW)
    assert not filters.fresh_enough(job(age_hours=24 * 10), settings.filters, NOW)
    assert filters.fresh_enough(job(age_hours=None), settings.filters, NOW)  # undated postings pass


def test_why_rejected_reports_reason(settings):
    assert filters.why_rejected(job(), settings.filters, NOW) is None
    assert filters.why_rejected(job("Nurse"), settings.filters, NOW) == "title"
    assert filters.why_rejected(job(location="Denver, CO"), settings.filters, NOW) == "location"
    assert filters.why_rejected(job(age_hours=500), settings.filters, NOW) == "too old"
