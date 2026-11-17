"""Send the alert: always to the console, plus email and/or phone push if configured.

Email (Gmail): SMTP_USER, SMTP_PASSWORD (a Gmail app password, not your normal password),
               ALERT_EMAIL_TO. Optional SMTP_HOST (default smtp.gmail.com), SMTP_PORT (465).
Phone push:    NTFY_TOPIC, a hard-to-guess topic name you subscribe to in the free ntfy app.
               Anyone who knows the topic name can read it, so use something random.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

import requests

from job_alert.models import Job

log = logging.getLogger(__name__)


def _line(job: Job) -> str:
    score = f"[{job.score}] " if job.score is not None else ""
    posted = job.posted_at.strftime("%b %d %H:%M UTC") if job.posted_at else "date unknown"
    return f"{score}{job.title} at {job.company} ({job.location or 'location n/a'}; posted {posted})\n  {job.url}"


def format_digest(jobs: list[Job]) -> str:
    blocks = []
    for job in jobs:
        block = _line(job)
        if job.score_reasons:
            block += "\n" + "\n".join(f"  - {r}" for r in job.score_reasons)
        blocks.append(block)
    return "\n\n".join(blocks)


def send_email(subject: str, body: str) -> bool:
    user, password, to = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD"), os.environ.get("ALERT_EMAIL_TO")
    if not (user and password and to):
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(body)
    host, port = os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    return True


def send_ntfy(jobs: list[Job]) -> bool:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    for job in jobs[:10]:  # one push per job so each one opens its own posting
        title = f"{job.title} at {job.company}"
        requests.post(
            f"{server}/{topic}",
            data=_line(job).encode(),
            headers={"Title": title.encode("ascii", "ignore").decode(), "Click": job.url, "Tags": "briefcase"},
            timeout=15,
        ).raise_for_status()
    return True


def notify(jobs: list[Job], dry_run: bool = False) -> None:
    if not jobs:
        return
    subject = f"{len(jobs)} new job match{'es' if len(jobs) != 1 else ''}"
    body = format_digest(jobs)
    print(f"\n=== {subject} ===\n{body}\n")
    if dry_run:
        return
    for name, send in (("email", lambda: send_email(subject, body)), ("ntfy", lambda: send_ntfy(jobs))):
        try:
            if send():
                log.info("Sent %s alert", name)
        except Exception as exc:
            log.error("Could not send %s alert: %s", name, exc)
