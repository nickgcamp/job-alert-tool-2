"""One fetcher per applicant tracking system (ATS).

Each module exposes:
    parse(company, payload) -> list[Job]   pure function, easy to unit test
    fetch(company, session, settings) -> list[Job]   does the HTTP call(s)
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from job_alert.config import Settings
from job_alert.fetchers import ashby, greenhouse, lever, workday
from job_alert.models import Company, Job

FETCHERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "workday": workday.fetch,
}

USER_AGENT = "job-alert-tool/0.1 (personal job search; low volume)"


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=None)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return session


def fetch_company(company: Company, session: requests.Session, settings: Settings) -> list[Job]:
    return FETCHERS[company.ats](company, session, settings)
