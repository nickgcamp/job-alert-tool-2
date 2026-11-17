import pytest

from job_alert.config import load_companies
from job_alert.detect import detect
from job_alert.models import Job
from job_alert.store import SeenStore


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://boards.greenhouse.io/examplecorp/jobs/4012345", ("greenhouse", "examplecorp")),
        ("https://job-boards.greenhouse.io/examplecorp", ("greenhouse", "examplecorp")),
        ("https://boards.greenhouse.io/embed/job_board?for=examplecorp", ("greenhouse", "examplecorp")),
        ("https://jobs.lever.co/examplestartup/a1b2c3", ("lever", "examplestartup")),
        ("https://jobs.eu.lever.co/exampleeu", ("lever", "eu:exampleeu")),
        ("https://jobs.ashbyhq.com/examplefintech/1111-2222", ("ashby", "examplefintech")),
        (
            "https://exampleretailer.wd5.myworkdayjobs.com/en-US/ExampleCareers/job/Minneapolis-MN/X_R1",
            ("workday", "https://exampleretailer.wd5.myworkdayjobs.com/ExampleCareers"),
        ),
    ],
)
def test_detect(url, expected):
    assert detect(url) == expected


def test_detect_unknown():
    with pytest.raises(ValueError):
        detect("https://careers.example.com/jobs")


def test_load_companies_skips_comments(tmp_path):
    p = tmp_path / "companies.csv"
    p.write_text("# comment\nname,ats,board,enabled\nAcme,greenhouse,acme,true\n# Off,lever,off,true\nBeta,lever,beta,false\n")
    companies = load_companies(p)
    assert [(c.name, c.enabled) for c in companies] == [("Acme", True), ("Beta", False)]


def test_load_companies_rejects_unknown_ats(tmp_path):
    p = tmp_path / "companies.csv"
    p.write_text("name,ats,board,enabled\nAcme,taleo,acme,true\n")
    with pytest.raises(ValueError):
        load_companies(p)


def _job(i):
    return Job(source="lever", company="Acme", external_id=str(i), title=f"Job {i}", location="MN", url="https://x")


def test_store_remembers_jobs(tmp_path):
    store = SeenStore(tmp_path / "seen.db", database_url="")
    assert store.count() == 0
    first = [_job(1), _job(2), _job(2)]
    assert [j.external_id for j in store.unseen(first)] == ["1", "2"]
    store.mark_seen(store.unseen(first), alerted={_job(1).key})
    assert store.count() == 2
    assert [j.external_id for j in store.unseen([_job(1), _job(3)])] == ["3"]
    store.mark_seen([_job(1)])  # duplicate insert is a no-op
    assert store.count() == 2
    store.close()
