"""Ashby public Job Posting API. Public, no key needed.

Docs: https://developers.ashbyhq.com/docs/public-job-posting-api
List endpoint: GET https://api.ashbyhq.com/posting-api/job-board/{board_name}
"""

from __future__ import annotations

from job_alert.models import Company, Job
from job_alert.textutil import parse_iso

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def parse(company: Company, payload: dict) -> list[Job]:
    jobs = []
    for j in payload.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locations = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        location = " / ".join(loc for loc in locations if loc)
        url = j.get("jobUrl") or j.get("applyUrl") or ""
        jobs.append(
            Job(
                source="ashby",
                company=company.name,
                # The docs don't promise an id field, so fall back to the job URL.
                external_id=str(j.get("id") or url),
                title=(j.get("title") or "").strip(),
                location=location,
                url=url,
                posted_at=parse_iso(j.get("publishedAt")),
                remote=bool(j.get("isRemote")) or (j.get("workplaceType") or "").lower() == "remote",
                description=j.get("descriptionPlain") or "",
            )
        )
    return jobs


def fetch(company: Company, session, settings) -> list[Job]:
    resp = session.get(API.format(slug=company.board), timeout=30)
    resp.raise_for_status()
    return parse(company, resp.json())
