import json
from pathlib import Path

import pytest

from job_alert.config import load_settings

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str):
        return json.loads((FIXTURES / name).read_text())

    return _load


@pytest.fixture
def settings():
    """The real config.yaml shipped with the repo, so tests catch config regressions too."""
    return load_settings(ROOT / "config.yaml")
