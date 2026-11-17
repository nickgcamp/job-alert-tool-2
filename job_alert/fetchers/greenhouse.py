"""Greenhouse Job Board API. Public, no key needed for GET.

Docs: https://developers.greenhouse.io/job-board.html
List endpoint: GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
"""

from __future__ import annotations

from job_alert.models import Company, Job
from job_alert.textutil import html_to_text, parse_iso

API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def parse(company: Company, payload: dict) -> list[Job]:
    jobs = []
    for j in payload.get("jobs", []):
        location = (j.get("location") or {}).get("name", "") or ""
        jobs.append(
            Job(
                source="greenhouse",
                company=company.name,
                external_id=str(j["id"]),
                title=j.get("title", "").strip(),
                location=location,
                url=j.get("absolute_url", ""),
                # The list response has updated_at; first_published only shows up on some boards.
                posted_at=parse_iso(j.get("first_published") or j.get("updated_at")),
                remote="remote" in location.lower(),
                description=html_to_text(j.get("content")),
            )
        )
    return jobs


def fetch(company: Company, session, settings) -> list[Job]:
    resp = session.get(API.format(slug=company.board), params={"content": "true"}, timeout=30)
    resp.raise_for_status()
    return parse(company, resp.json())
