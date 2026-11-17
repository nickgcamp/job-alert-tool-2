"""Turn a company's careers-page URL into a companies.csv row.

    python -m job_alert detect https://boards.greenhouse.io/acme https://acme.wd5.myworkdayjobs.com/en-US/Careers

Tip: open the company's careers page, click into any job, and copy that URL. The job page
usually sits on the ATS's own domain even when the careers landing page doesn't.
"""

from __future__ import annotations

from urllib.parse import urlparse

from job_alert.fetchers.workday import parse_site


def detect(url: str) -> tuple[str, str]:
    """Return (ats, board) for a job board URL, or raise ValueError."""
    u = urlparse(url if "://" in url else f"https://{url}")
    host = u.netloc.lower().removeprefix("www.")
    parts = [p for p in u.path.split("/") if p]

    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io", "boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io"}:
        if parts and parts[0] != "embed":
            return "greenhouse", parts[0]
        for q in u.query.split("&"):  # embed form: .../embed/job_board?for=acme
            if q.startswith("for="):
                return "greenhouse", q[4:]
    if host == "boards-api.greenhouse.io" and len(parts) >= 3 and parts[1] == "boards":
        return "greenhouse", parts[2]
    if host == "jobs.lever.co" and parts:
        return "lever", parts[0]
    if host == "jobs.eu.lever.co" and parts:
        return "lever", f"eu:{parts[0]}"
    if host == "jobs.ashbyhq.com" and parts:
        return "ashby", parts[0]
    if host.endswith(".myworkdayjobs.com"):
        site = parse_site(url)
        return "workday", f"https://{site.host}/{site.site}"
    raise ValueError(f"Couldn't tell which job board this is: {url}")


def main(urls: list[str]) -> int:
    print("name,ats,board,enabled")
    failed = 0
    for url in urls:
        try:
            ats, board = detect(url)
        except ValueError as exc:
            print(f"# {exc}")
            failed += 1
            continue
        name = board.split("/")[-1] if ats == "workday" else board.removeprefix("eu:")
        print(f"{name},{ats},{board},true")
    return 1 if failed else 0
