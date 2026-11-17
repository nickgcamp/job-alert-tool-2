"""End-to-end run with the network faked out: seed first, then only new matches alert."""

from datetime import datetime, timezone

from job_alert import pipeline
from job_alert.models import Company, Job
from job_alert.store import SeenStore


def _job(i, title="Financial Analyst", location="Minneapolis, MN"):
    return Job(
        source="lever", company="Acme", external_id=str(i), title=title, location=location,
        url=f"https://jobs.lever.co/acme/{i}", posted_at=datetime.now(timezone.utc),
    )


def test_seed_then_alert_only_new(tmp_path, settings, monkeypatch, capsys):
    board = [_job(1), _job(2, title="Software Engineer")]
    monkeypatch.setattr(pipeline, "fetch_all", lambda companies, s: (list(board), 0))
    store = SeenStore(tmp_path / "seen.db", database_url="")
    companies = [Company("Acme", "lever", "acme")]

    first = pipeline.run(companies, settings, store)
    assert first.seeded and first.alerted == 0 and store.count() == 2

    board.extend([_job(3), _job(4, location="Paris, France")])
    second = pipeline.run(companies, settings, store)
    assert (second.new, second.matched, second.alerted) == (2, 1, 1)
    assert "https://jobs.lever.co/acme/3" in capsys.readouterr().out

    third = pipeline.run(companies, settings, store)
    assert third.new == 0 and third.alerted == 0
    store.close()


def test_dry_run_saves_nothing(tmp_path, settings, monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_all", lambda companies, s: ([_job(1)], 0))
    store = SeenStore(tmp_path / "seen.db", database_url="")
    summary = pipeline.run([Company("Acme", "lever", "acme")], settings, store, dry_run=True, seed=False)
    assert summary.alerted == 1 and store.count() == 0
    store.close()
