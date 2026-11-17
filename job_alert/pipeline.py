"""One run: fetch every board, keep new matches, score them, alert, remember them."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from job_alert import filters
from job_alert.config import Settings
from job_alert.fetchers import fetch_company, make_session, workday
from job_alert.models import Company, Job
from job_alert.notifier import notify
from job_alert.scorer import Scorer, load_resume
from job_alert.store import SeenStore

log = logging.getLogger(__name__)


@dataclass
class RunSummary:
    fetched: int = 0
    new: int = 0
    matched: int = 0
    alerted: int = 0
    failed_companies: int = 0
    seeded: bool = False


def fetch_all(companies: list[Company], settings: Settings, workers: int = 8) -> tuple[list[Job], int]:
    session = make_session()
    jobs: list[Job] = []
    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_company, c, session, settings): c for c in companies if c.enabled}
        for fut in as_completed(futures):
            company = futures[fut]
            try:
                got = fut.result()
                log.info("%-28s %-10s %4d jobs", company.name, company.ats, len(got))
                jobs.extend(got)
            except Exception as exc:  # one broken board shouldn't sink the run
                failed += 1
                log.error("%s (%s): %s", company.name, company.ats, exc)
    return jobs, failed


def run(
    companies: list[Company],
    settings: Settings,
    store: SeenStore,
    *,
    dry_run: bool = False,
    seed: bool | None = None,
) -> RunSummary:
    summary = RunSummary()
    jobs, summary.failed_companies = fetch_all(companies, settings)
    summary.fetched = len(jobs)

    new_jobs = store.unseen(jobs)
    summary.new = len(new_jobs)

    # First run: remember everything that's already posted without alerting, so you
    # only hear about jobs that appear from now on.
    if seed is None:
        seed = store.count() == 0
    if seed:
        summary.seeded = True
        if not dry_run:
            store.mark_seen(new_jobs)
        log.info("Seed run: stored %d existing postings, no alerts sent.", len(new_jobs))
        return summary

    matches = filters.apply_filters(new_jobs, settings.filters)
    summary.matched = len(matches)

    if matches and settings.scoring.enabled:
        resume = load_resume()
        if not resume:
            log.warning("Scoring is on but no resume found (set RESUME_TEXT or add resume.txt). Skipping scores.")
        else:
            scorer = Scorer(settings.scoring, resume)
            session = make_session()
            for job in matches:
                if job.source == "workday" and not job.description:
                    try:
                        workday.add_description(job, session)
                    except Exception as exc:
                        log.warning("No Workday description for %s: %s", job.key, exc)
                scorer.score(job)
            matches = [j for j in matches if j.score is None or j.score >= settings.scoring.min_score]

    matches.sort(key=lambda j: (j.score is not None, j.score or 0), reverse=True)
    notify(matches, dry_run=dry_run)
    summary.alerted = len(matches)

    if not dry_run:
        store.mark_seen(new_jobs, alerted={j.key for j in matches})
    return summary
