"""Optional: score each matching posting against your resume with Claude.

Turned on by `scoring.enabled: true` in config.yaml plus an ANTHROPIC_API_KEY env var.
Your resume text comes from RESUME_TEXT (env var / GitHub secret) or the file at RESUME_PATH
(default resume.txt, which .gitignore keeps out of the repo).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from job_alert.config import ScoringConfig
from job_alert.models import Job

log = logging.getLogger(__name__)

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "description": "0-100 fit for this candidate"},
        "reasons": {"type": "array", "items": {"type": "string"}, "description": "2-3 short reasons"},
    },
    "required": ["score", "reasons"],
    "additionalProperties": False,
}

SYSTEM = """You screen job postings for one candidate whose resume is below.
Score how well each posting fits them from 0 to 100:
90+ apply today, 70-89 strong fit, 50-69 possible stretch, under 50 skip.
Weigh the role family and level, required skills and years of experience, industry, and
location or remote rules. Give 2 or 3 short, specific reasons, naming any dealbreaker.

<resume>
{resume}
</resume>"""


def load_resume() -> str | None:
    text = os.environ.get("RESUME_TEXT")
    if text:
        return text
    path = Path(os.environ.get("RESUME_PATH", "resume.txt"))
    return path.read_text() if path.exists() else None


class Scorer:
    def __init__(self, cfg: ScoringConfig, resume: str):
        import anthropic  # optional dependency, only needed when scoring is on

        self.cfg = cfg
        self.client = anthropic.Anthropic()
        self.system = [{"type": "text", "text": SYSTEM.format(resume=resume), "cache_control": {"type": "ephemeral"}}]

    def score(self, job: Job) -> Job:
        posting = (
            f"Company: {job.company}\nTitle: {job.title}\nLocation: {job.location}"
            f"{' (remote)' if job.remote else ''}\nURL: {job.url}\n\n"
            f"Description:\n{job.description or '(not available, judge from the title)'}"
        )
        try:
            response = self.client.beta.messages.create(
                model=self.cfg.model,
                max_tokens=2000,
                # If a safety check declines on the main model, retry on a fallback model in the same call.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=self.system,
                messages=[{"role": "user", "content": posting}],
                output_config={"effort": self.cfg.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            )
            if response.stop_reason == "refusal":
                log.warning("Scoring declined for %s", job.key)
                return job
            text = next(b.text for b in response.content if b.type == "text")
            data = json.loads(text)
            job.score = max(0, min(100, int(data["score"])))
            job.score_reasons = [str(r) for r in data.get("reasons", [])][:3]
        except Exception as exc:  # scoring is a bonus; never block the alert on it
            log.warning("Scoring failed for %s: %s", job.key, exc)
        return job
