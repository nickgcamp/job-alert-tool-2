"""Command line entry point.

    python -m job_alert run                 # normal run (first run seeds silently)
    python -m job_alert run --dry-run       # print matches, send nothing, save nothing
    python -m job_alert run --no-seed       # alert on everything that matches, even on run one
    python -m job_alert detect URL [URL..]  # careers URL -> companies.csv row
"""

from __future__ import annotations

import argparse
import logging

from job_alert import detect as detect_mod
from job_alert.config import load_companies, load_settings
from job_alert.pipeline import run
from job_alert.store import SeenStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job_alert", description="Alert on new job postings within the hour.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="fetch boards, alert on new matches")
    p_run.add_argument("--config", default="config.yaml")
    p_run.add_argument("--companies", default="companies.csv")
    p_run.add_argument("--db", default="data/seen_jobs.db", help="SQLite file (ignored when DATABASE_URL is set)")
    p_run.add_argument("--dry-run", action="store_true", help="print matches only; don't send or save")
    seed = p_run.add_mutually_exclusive_group()
    seed.add_argument("--seed", dest="seed", action="store_true", default=None, help="store current jobs, no alerts")
    seed.add_argument("--no-seed", dest="seed", action="store_false", help="alert even if the database is empty")
    p_run.add_argument("-v", "--verbose", action="store_true")

    p_detect = sub.add_parser("detect", help="turn careers-page URLs into companies.csv rows")
    p_detect.add_argument("urls", nargs="+")

    args = parser.parse_args(argv)

    if args.cmd == "detect":
        return detect_mod.main(args.urls)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    settings = load_settings(args.config)
    companies = load_companies(args.companies)
    store = SeenStore(args.db)
    try:
        s = run(companies, settings, store, dry_run=args.dry_run, seed=args.seed)
    finally:
        store.close()
    logging.info(
        "Done: %d fetched, %d new, %d matched, %d alerted, %d boards failed%s",
        s.fetched, s.new, s.matched, s.alerted, s.failed_companies, " (seed run)" if s.seeded else "",
    )
    # Fail the scheduled job only if every board failed, so you notice a real outage.
    enabled = sum(c.enabled for c in companies)
    return 1 if enabled and s.failed_companies == enabled else 0
