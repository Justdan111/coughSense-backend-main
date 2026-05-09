"""Unit tests for app.api.analysis.triage_guidance."""
from __future__ import annotations

import pytest

from app.api.analysis import triage_guidance


@pytest.mark.parametrize("result", ["risky", "less_risky"])
def test_triage_guidance_returns_required_keys(result: str):
    out = triage_guidance(result)
    assert set(out.keys()) >= {"summary", "recommendation", "actions"}
    assert isinstance(out["actions"], list)
    assert len(out["actions"]) > 0


def test_triage_guidance_risky_mentions_blood():
    out = triage_guidance("risky")
    joined = " ".join(out["actions"]).lower()
    assert "blood" in joined
    assert "medical" in out["recommendation"].lower()


def test_triage_guidance_less_risky_advises_monitoring():
    out = triage_guidance("less_risky")
    joined = " ".join(out["actions"]).lower()
    assert "monitor" in joined or "rest" in joined
    assert "no urgent" in out["recommendation"].lower() or "stay alert" in out["recommendation"].lower()


def test_triage_guidance_unknown_falls_through_to_less_risky():
    """Implementation: anything not == 'risky' returns the less_risky branch."""
    out = triage_guidance("anything-else")
    assert "lower" in out["summary"].lower()
