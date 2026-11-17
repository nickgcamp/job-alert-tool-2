"""Lever Postings API. Public, no key needed.

List endpoint: GET https://api.lever.co/v0/postings/{site}?mode=json
EU-hosted boards use api.eu.lever.co; put "eu:<site>" in the board column for those.
"""

from __future__ import annotations

from job_alert.models import Company, Job
from job_alert.textutil import from_epoch_ms

API_US = "https://api.lever.co/v0/postings/{slug}"
API_EU = "https://api.eu.lever.co/v0/postings/{slug}"
PAGE = 100


def parse(company: Company, payload: list) -> list[Job]:
    jobs = []
    for j in payload:
        cats = j.get("categories") or {}
        location = cats.get("location") or ", ".join(cats.get("allLocations") or []) or ""
        workplace = (j.get("workplaceType") or "").lower()
        jobs.append(
            Job(
                source="lever",
                company=company.name,
                external_id=str(j["id"]),
                title=(j.get("text") or "").strip(),
                location=location,
                url=j.get("hostedUrl") or j.get("applyUrl") or "",
                posted_at=from_epoch_ms(j.get("createdAt")),
                remote=workplace == "remote" or "remote" in location.lower(),
                description=j.get("descriptionPlain") or "",
            )
        )
    return jobs


def fetch(company: Company, session, settings) -> list[Job]:
    board = company.board
    api = API_EU if board.startswith("eu:") else API_US
    slug = board.removeprefix("eu:")
    jobs: list[Job] = []
    skip = 0
    while True:
        resp = session.get(api.format(slug=slug), params={"mode": "json", "skip": skip, "limit": PAGE}, timeout=30)
        resp.raise_for_status()
        page = resp.json()
        jobs.extend(parse(company, page))
        if len(page) < PAGE:
            return jobs
        skip += PAGE
