# job-alert-tool

Get an alert within about an hour of a matching job going live, straight from the
companies' own job boards, before it shows up on the big aggregators.

Applying early matters: many postings get most of their applicants in the first few days,
and recruiters often start screening the first batch. This tool checks the boards of the
companies you pick every hour, keeps only new postings that match your titles and
locations, optionally scores each one against your resume with Claude, and emails or
pushes them to your phone.

```
companies.csv ──► fetchers ──► seen-jobs DB ──► filters ──► (Claude fit score) ──► email / phone push
 (you edit)      Greenhouse     "is this new?"   title,      optional, 0-100       digest, best first
                 Lever          SQLite or        location,
                 Ashby          Postgres         freshness
                 Workday
```

## Why go to the source

Job aggregators re-list postings hours or days after a company publishes them. Most
companies run their careers page on an applicant tracking system (ATS), and the big ones
publish the same data as JSON for their own career widgets:

| ATS | Endpoint | Key needed? | Notes |
| --- | --- | --- | --- |
| Greenhouse | `GET boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` | No | [Official docs](https://docs.greenhouse.io/job-board.html). Public GET endpoints need no auth. |
| Lever | `GET api.lever.co/v0/postings/{site}?mode=json` | No | Public postings API. EU boards use `api.eu.lever.co`. |
| Ashby | `GET api.ashbyhq.com/posting-api/job-board/{board}` | No | [Official docs](https://developers.ashbyhq.com/docs/public-job-posting-api). |
| Workday | `POST {tenant}.wdN.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | No | **Not an official API.** It's what Workday career pages call. It can change without notice, needs `limit` ≤ 20, and dates are text like "Posted 3 Days Ago". |

Large employers mostly use Workday; startups and mid-size tech mostly use Greenhouse,
Lever or Ashby. Together these cover a big share of the market.

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q                                  # 51 tests, no network needed

# 1. Add companies (see "Choosing companies" below)
python -m job_alert detect "<a job posting URL from the company's careers page>"
#    ...paste the printed row into companies.csv

# 2. First run: stores everything already posted, sends nothing
python -m job_alert run

# 3. Every run after that alerts only on new matches
python -m job_alert run --dry-run -v       # preview without saving or sending
```

The first run is a silent "seed" on purpose, so you don't get 300 alerts for jobs that
have been up for weeks. Use `--no-seed` if you do want everything that matches today.
The same goes for any board the first time it answers, whether you just added it or it
was failing before: its existing postings are stored quietly, and only later ones alert.

## Choosing companies

`companies.csv` has one row per board:

```csv
name,ats,board,enabled
Example Corp,greenhouse,examplecorp,true
Example Retailer,workday,https://exampleretailer.wd5.myworkdayjobs.com/ExampleCareers,true
```

To find a company's board: open its careers page, click into any posting and copy that
URL. Then `python -m job_alert detect <url>` tells you the ATS and prints the row. If it
says it can't tell, the company uses another system (Taleo, iCIMS, SuccessFactors and so
on), which this version doesn't support yet.

For Twin Cities FP&A roles, good places to start are the large local employers (retail,
food, medical devices, banking, insurance, logistics, healthcare) and the region's growing
fintech and SaaS companies. A list of 20 to 40 boards is plenty for an hourly check.

## What counts as a match

Everything lives in `config.yaml`:

- `include_titles` / `exclude_titles`: case-insensitive whole phrases. `fp&a` matches
  "Sr. FP&A Analyst" but `vp` doesn't match "VPN".
- `locations`: a job passes if its location matches one of these, or it's remote and
  `remote_ok` is true. `exclude_locations` always wins.
- `max_age_hours`: skips older postings when the board gives a date.
- `workday.search_terms`: Workday has no "list everything" call, so each Workday site is
  searched with these terms.

## Alerts

Set whichever you want as environment variables (locally in `.env`, copied from
`.env.example`; in GitHub as repository secrets):

- **Email through Gmail:** `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO`. The password is a
  Gmail app password (Google Account → Security → App passwords), which needs
  2-Step Verification turned on. Never use your real Gmail password.
- **Phone push through ntfy (ntfy.sh):** `NTFY_TOPIC`. Install the free ntfy app,
  subscribe to a long random topic name, and use the same name here. Anyone who knows the
  name can read it, so make it unguessable. Each push opens the posting when tapped.

Every run also prints matches to the log.

## Fit scoring with Claude (optional)

With `scoring.enabled: true`, each match is sent to Claude with your resume and comes back
with a 0 to 100 fit score and two or three reasons. Matches under `min_score` are dropped
and the rest are sorted best first.

Needs `ANTHROPIC_API_KEY` and your resume as plain text in `RESUME_TEXT` (a GitHub secret
works) or in `resume.txt`, which `.gitignore` keeps out of the repo. Uses
`claude-opus-5-5` at `low` effort with JSON-schema structured output, prompt caching on
the resume, and a server-side fallback if a request is declined. Scoring only runs on
postings that already passed the filters, so the cost stays small. A failed score never
blocks an alert.

## Run it every hour on GitHub Actions (free for public repos)

`.github/workflows/job-alert.yml` runs `python -m job_alert run` at 17 minutes past every
hour, and you can also start it by hand from the Actions tab.

1. Push this folder to a new GitHub repo.
2. Add the secrets you're using under **Settings → Secrets and variables → Actions**.
3. Open **Actions → job-alert → Run workflow** once. That first run seeds the database.

The seen-jobs SQLite file is kept in the Actions cache between runs, so it never gets
committed to the public repo. If the cache is ever evicted, the next run simply seeds
again without alerting. For a permanent store, set `DATABASE_URL` to a Postgres database
(free tiers exist) and `pip install "psycopg[binary]"`.

GitHub may start scheduled runs a few minutes late, and it pauses scheduled workflows in a
public repo after 60 days with no commits. Push any small change to wake it up.

## Project layout

```
job_alert/
  fetchers/      one module per ATS: parse() is pure, fetch() does HTTP
  filters.py     title, location, freshness rules
  store.py       seen-jobs table (SQLite or Postgres)
  scorer.py      optional Claude fit score
  notifier.py    console, email, ntfy
  pipeline.py    one run, start to finish
  detect.py      careers URL -> companies.csv row
  cli.py         `python -m job_alert run | detect`
tests/           fixtures for each ATS plus filter, store, scorer and pipeline tests
```

## Design notes

- **Dedupe on a stable key** (`source:company:job id`), not on title, because companies
  repost the same title with a new id when they open a second seat, and that's worth knowing.
- **Seed before alerting** so the tool only reports genuinely new postings.
- **One broken board doesn't stop the run.** The scheduled job only fails if every board
  fails, which is the signal that something real broke.
- **Polite by default:** one request per board per hour (a few more for Workday), retries
  with backoff, and an honest User-Agent. Workday seems to rate-limit by IP across all of
  its customers' sites, so Workday boards are checked one at a time, 2 seconds apart,
  while the other boards run in parallel.
- **Fetchers are tested against saved responses**, built from each ATS's documented fields,
  so the test suite runs without network access.

## Ideas for next steps

- More ATSs: SmartRecruiters and Recruitee also have public posting feeds.
- A small dashboard of postings over time per company (who's hiring finance, and how fast
  roles close).
- Draft a tailored cover letter for high-scoring matches.
- Track time from posting to your application.

## Responsible use

This reads the same public data the companies' own career pages load. Keep the schedule
modest, respect each site's terms, and don't use it to mass-apply.
