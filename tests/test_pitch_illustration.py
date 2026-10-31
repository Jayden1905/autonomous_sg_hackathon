"""The decision-time illustration is quoted in PITCH.md; these pin the numbers it quotes."""

from pathlib import Path

from atc_negotiation import fallback
from atc_negotiation.rules import evaluate
from atc_negotiation.schemas import Proposal, Scenario

SCEN = Path(__file__).parent.parent / "scenarios" / "demo_hold_ua599_decision_time.json"


def _legal_on(s, runway, gate, lo, hi):
    return [t for t in range(lo, hi + 1)
            if evaluate(s, Proposal(arrival_min=t, runway=runway, gate=gate, rationale="")).feasible]


def test_illustration_is_labelled_and_not_a_dataset_row():
    s = Scenario.model_validate_json(SCEN.read_text())
    assert s.source == {}
    assert any("illustration" in f.lower() for f in s.synthetic_fields)
    assert "ILLUSTRATION" in s.disruption


def test_legal_slots_match_the_pitch():
    s = Scenario.model_validate_json(SCEN.read_text())
    assert _legal_on(s, "27R", "C9", 1, 30) == [4, 5, 9, 13]
    best = fallback.solve(s)
    assert (best.proposal.arrival_min, best.proposal.runway, best.proposal.gate) == (4, "27R", "C9")


def test_ten_minute_phone_chain_costs_three_slots_not_passengers():
    s = Scenario.model_validate_json(SCEN.read_text())
    fast, slow = 4, 13  # first legal slot overall vs first legal slot once 10 min have passed
    assert min(t for t in _legal_on(s, "27R", "C9", 10, 30)) == slow
    for t in (fast, slow):
        missed = sum(c.passengers for c in s.connections if t + c.min_connect_min > c.departs_min)
        assert missed == 0
    assert (slow - s.earliest_arrival_min) - (fast - s.earliest_arrival_min) == 9  # 9 extra minutes holding
