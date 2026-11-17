"""Remember which postings we've already seen, so you're only alerted once per job.

SQLite by default (a single file, zero setup). Set DATABASE_URL=postgresql://... to use
Postgres instead (pip install "psycopg[binary]"), e.g. a free hosted Postgres.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from job_alert.models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    job_key       TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    location      TEXT,
    url           TEXT,
    posted_at     TEXT,
    first_seen_at TEXT NOT NULL,
    alerted       INTEGER NOT NULL DEFAULT 0,
    score         INTEGER
)
"""


class SeenStore:
    def __init__(self, sqlite_path: str | Path = "data/seen_jobs.db", database_url: str | None = None):
        database_url = database_url if database_url is not None else os.environ.get("DATABASE_URL")
        if database_url:
            import psycopg  # optional dependency

            self.conn = psycopg.connect(database_url, autocommit=True)
            self.ph = "%s"
        else:
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(sqlite_path))
            self.ph = "?"
        self._exec(SCHEMA)

    def _exec(self, sql: str, params: tuple = ()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur

    def count(self) -> int:
        return self._exec("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]

    def unseen(self, jobs: list[Job]) -> list[Job]:
        """Jobs whose key isn't stored yet, in their original order, without duplicates."""
        out, keys = [], set()
        for job in jobs:
            if job.key in keys:
                continue
            keys.add(job.key)
            row = self._exec(f"SELECT 1 FROM seen_jobs WHERE job_key = {self.ph}", (job.key,)).fetchone()
            if row is None:
                out.append(job)
        return out

    def mark_seen(self, jobs: list[Job], alerted: set[str] | None = None) -> None:
        alerted = alerted or set()
        now = datetime.now(timezone.utc).isoformat()
        sql = (
            "INSERT INTO seen_jobs (job_key, source, company, title, location, url, posted_at, first_seen_at, alerted, score) "
            f"VALUES ({', '.join([self.ph] * 10)}) ON CONFLICT (job_key) DO NOTHING"
        )
        for j in jobs:
            self._exec(
                sql,
                (
                    j.key, j.source, j.company, j.title, j.location, j.url,
                    j.posted_at.isoformat() if j.posted_at else None,
                    now, int(j.key in alerted), j.score,
                ),
            )
        if isinstance(self.conn, sqlite3.Connection):
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()
