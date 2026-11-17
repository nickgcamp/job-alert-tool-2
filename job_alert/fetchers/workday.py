"""Workday career sites (many large Twin Cities employers use these).

Workday has no official public jobs API. Its career pages call a JSON endpoint that works
without a key, but it isn't a documented contract and can change without notice:

    POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "financial analyst"}

Gotchas handled here:
  * limit must be 20 or less (bigger values silently return zero jobs)
  * postedOn is display text ("Posted Today", "Posted 3 Days Ago"), not a date
Keep request volume low: a few search terms, a few pages, once an hour.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from job_alert.models import Company, Job
from job_alert.textutil import html_to_text, parse_iso

PAGE = 20
_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


@dataclass(frozen=True)
class WorkdaySite:
    host: str  # e.g. acme.wd5.myworkdayjobs.com
    tenant: str  # e.g. acme
    site: str  # e.g. AcmeCareers

    @property
    def api(self) -> str:
        return f"https://{self.host}/wday/cxs/{self.tenant}/{self.site}/jobs"

    def job_url(self, external_path: str) -> str:
        return f"https://{self.host}/{self.site}{external_path}"


def parse_site(board: str) -> WorkdaySite:
    """Turn a careers URL like https://acme.wd5.myworkdayjobs.com/en-US/AcmeCareers into its parts."""
    url = urlparse(board if "://" in board else f"https://{board}")
    host = url.netloc.lower()
    if not host.endswith(".myworkdayjobs.com"):
        raise ValueError(f"Not a myworkdayjobs.com URL: {board}")
    parts = [p for p in url.path.split("/") if p and not _LOCALE.match(p)]
    if not parts:
        raise ValueError(f"Workday URL is missing the site name after the host: {board}")
    return WorkdaySite(host=host, tenant=host.split(".")[0], site=parts[0])


def parse_posted_on(text: str | None, now: datetime | None = None) -> datetime | None:
    """'Posted Today' -> now, 'Posted 3 Days Ago' -> now-3d, 'Posted 30+ Days Ago' -> now-30d."""
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    t = text.lower()
    if "today" in t:
        return now
    if "yesterday" in t:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*day", t)
    if m:
        return now - timedelta(days=int(m.group(1)))
    return None


def parse(company: Company, payload: dict, site: WorkdaySite, now: datetime | None = None) -> list[Job]:
    jobs = []
    for j in payload.get("jobPostings", []):
        path = j.get("externalPath") or ""
        if not path:
            continue
        location = j.get("locationsText") or ""
        bullets = " ".join(j.get("bulletFields") or [])
        jobs.append(
            Job(
                source="workday",
                company=company.name,
                external_id=path.rsplit("/", 1)[-1] or path,
                title=(j.get("title") or "").strip(),
                location=location,
                url=site.job_url(path),
                posted_at=parse_posted_on(j.get("postedOn"), now),
                remote="remote" in f"{location} {bullets}".lower(),
            )
        )
    return jobs


def fetch(company: Company, session, settings) -> list[Job]:
    site = parse_site(company.board)
    terms = settings.workday_search_terms or [""]
    found: dict[str, Job] = {}
    for term in terms:
        for page in range(settings.workday_max_pages):
            body = {"appliedFacets": {}, "limit": PAGE, "offset": page * PAGE, "searchText": term}
            resp = session.post(
                site.api, json=body, headers={"Accept-Language": "en-US", "Content-Type": "application/json"}, timeout=30
            )
            resp.raise_for_status()
            payload = resp.json()
            batch = parse(company, payload, site)
            for job in batch:
                found.setdefault(job.key, job)
            if len(payload.get("jobPostings") or []) < PAGE:
                break
    return list(found.values())


def add_description(job: Job, session) -> Job:
    """The list call has no description. Fetch it for jobs that passed the filters (one request each)."""
    site = parse_site(job.url)
    prefix = f"https://{site.host}/{site.site}"
    if not job.url.startswith(prefix):
        return job
    detail_url = f"https://{site.host}/wday/cxs/{site.tenant}/{site.site}{job.url[len(prefix):]}"
    resp = session.get(detail_url, headers={"Accept": "application/json", "Accept-Language": "en-US"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    info = data.get("jobPostingInfo") or data
    job.description = html_to_text(info.get("jobDescription"))
    real_start = parse_iso(info.get("startDate"))
    if real_start and job.posted_at is None:
        job.posted_at = real_start
    return job
