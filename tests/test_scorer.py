"""Scorer logic with a fake Claude client (no API key or network needed)."""

from types import SimpleNamespace

from job_alert.config import ScoringConfig
from job_alert.models import Job
from job_alert.scorer import Scorer


class FakeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def make_scorer(response):
    scorer = Scorer.__new__(Scorer)  # skip __init__ so the anthropic package isn't required
    scorer.cfg = ScoringConfig(enabled=True)
    scorer.system = [{"type": "text", "text": "resume"}]
    scorer.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(response)))
    return scorer


def job():
    return Job(source="lever", company="Acme", external_id="1", title="FP&A Analyst", location="MN", url="https://x")


def test_score_parsed_and_clamped():
    text = SimpleNamespace(type="text", text='{"score": 140, "reasons": ["a", "b", "c", "d"]}')
    scorer = make_scorer(SimpleNamespace(stop_reason="end_turn", content=[text]))
    j = scorer.score(job())
    assert j.score == 100 and j.score_reasons == ["a", "b", "c"]
    call = scorer.client.beta.messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"


def test_refusal_leaves_job_unscored():
    scorer = make_scorer(SimpleNamespace(stop_reason="refusal", content=[]))
    assert scorer.score(job()).score is None


def test_api_error_never_raises():
    scorer = make_scorer(None)
    scorer.client.beta.messages.create = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
    assert scorer.score(job()).score is None
