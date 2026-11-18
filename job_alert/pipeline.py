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
    """Greenhouse, Lever and Ashby boards run in parallel; Workday sites run one at a time
    (they share a rate limit), alongside the others."""
    session = make_session()
    jobs: list[Job] = []
    failed = 0
    enabled = [c for c in companies if c.enabled]
    parallel = [c for c in enabled if c.ats != "workday"]
    serial = [c for c in enabled if c.ats == "workday"]

    def fetch_serial() -> list[tuple[Company, list[Job] | Exception]]:
        out = []
        for c in serial:
            try:
                out.append((c, fetch_company(c, session, settings)))
            except Exception as exc:
                out.append((c, exc))
        return out

    def record(company: Company, result) -> None:
        nonlocal failed
        if isinstance(result, Exception):  # one broken board shouldn't sink the run
            failed += 1
            log.error("%s (%s): %s", company.name, company.ats, result)
        else:
            log.info("%-28s %-10s %4d jobs", company.name, company.ats, len(result))
            jobs.extend(result)

    with ThreadPoolExecutor(max_workers=workers + 1) as pool:
        serial_future = pool.submit(fetch_serial)
        futures = {pool.submit(fetch_company, c, session, settings): c for c in parallel}
        for fut in as_completed(futures):
            try:
                record(futures[fut], fut.result())
            except Exception as exc:
                record(futures[fut], exc)
        for company, result in serial_future.result():
            record(company, result)
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

    known_boards = store.known_boards()
    new_jobs = store.unseen(jobs)
    summary.new = len(new_jobs)

    # First run: remember everything that's already posted without alerting, so you
    # only hear about jobs that appear from now on.
    auto_seed = seed is None
    if auto_seed:
        seed = store.count() == 0
    if seed:
        summary.seeded = True
        if not dry_run:
            store.mark_seen(new_jobs)
        log.info("Seed run: stored %d existing postings, no alerts sent.", len(new_jobs))
        return summary

    # A board that has never returned jobs before (it failed on earlier runs, or you just added
    # it) gets seeded silently too, so it doesn't flood you with its whole backlog.
    # --no-seed turns this off along with the first-run seed.
    first_time = [j for j in new_jobs if auto_seed and (j.source, j.company.lower()) not in known_boards]
    if first_time:
        boards = sorted({j.company for j in first_time})
        log.info("First successful check of %s: stored %d postings, no alerts.", ", ".join(boards), len(first_time))
    first_keys = {j.key for j in first_time}
    candidates = [j for j in new_jobs if j.key not in first_keys]

    matches = filters.apply_filters(candidates, settings.filters)
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
