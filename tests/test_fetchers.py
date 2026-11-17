from datetime import datetime, timedelta, timezone

import pytest

from job_alert.fetchers import ashby, greenhouse, lever, workday
from job_alert.models import Company

NOW = datetime(2026, 11, 17, 23, 0, tzinfo=timezone.utc)


def test_greenhouse(load_fixture):
    jobs = greenhouse.parse(Company("Example Corp", "greenhouse", "examplecorp"), load_fixture("greenhouse.json"))
    assert len(jobs) == 2
    j = jobs[0]
    assert j.key == "greenhouse:example corp:4012345"
    assert j.title == "Senior Financial Analyst, FP&A"
    assert j.location == "Minneapolis, MN"
    assert j.posted_at == datetime(2026, 11, 17, 20, 0, tzinfo=timezone.utc)
    assert "forecast & budget" in j.description and "<" not in j.description
    assert jobs[1].remote is True


def test_lever(load_fixture):
    jobs = lever.parse(Company("Example Startup", "lever", "examplestartup"), load_fixture("lever.json"))
    assert [j.title for j in jobs] == ["FP&A Analyst", "Account Executive"]
    assert jobs[0].remote is True and jobs[1].remote is False
    assert jobs[0].url == "https://jobs.lever.co/examplestartup/a1b2c3"
    assert jobs[0].posted_at.tzinfo is not None


def test_ashby_skips_unlisted_and_uses_url_as_id(load_fixture):
    jobs = ashby.parse(Company("Example Fintech", "ashby", "examplefintech"), load_fixture("ashby.json"))
    assert len(jobs) == 1
    j = jobs[0]
    assert j.external_id == "https://jobs.ashbyhq.com/examplefintech/1111-2222"
    assert j.location == "St. Paul, MN / Remote (US)"
    assert j.posted_at == datetime(2026, 11, 17, 18, 30, tzinfo=timezone.utc)


def test_workday(load_fixture):
    site = workday.parse_site("https://exampleretailer.wd5.myworkdayjobs.com/en-US/ExampleCareers")
    assert site.api == "https://exampleretailer.wd5.myworkdayjobs.com/wday/cxs/exampleretailer/ExampleCareers/jobs"
    jobs = workday.parse(Company("Example Retailer", "workday", "x"), load_fixture("workday.json"), site, now=NOW)
    assert jobs[0].external_id == "Financial-Analyst-II_R0012345"
    assert jobs[0].url == "https://exampleretailer.wd5.myworkdayjobs.com/ExampleCareers/job/Minneapolis-MN/Financial-Analyst-II_R0012345"
    assert jobs[0].posted_at == NOW
    assert jobs[1].posted_at == NOW - timedelta(days=30)


@pytest.mark.parametrize(
    "text,days",
    [("Posted Today", 0), ("Posted Yesterday", 1), ("Posted 3 Days Ago", 3), ("Posted 30+ Days Ago", 30)],
)
def test_workday_posted_on(text, days):
    assert workday.parse_posted_on(text, NOW) == NOW - timedelta(days=days)


def test_workday_posted_on_unknown():
    assert workday.parse_posted_on("", NOW) is None
    assert workday.parse_posted_on("Posted sometime", NOW) is None


def test_workday_bad_url():
    with pytest.raises(ValueError):
        workday.parse_site("https://example.com/careers")
