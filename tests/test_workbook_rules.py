"""Workbook rules: gate change notice (20 min) and flight crew duty (13 h)."""

from pathlib import Path

from atc_negotiation import rules
from atc_negotiation.schemas import Proposal, Scenario

ROOT = Path(__file__).resolve().parents[1]


def _scenario(**update) -> Scenario:
    s = Scenario.model_validate_json((ROOT / "scenarios" / "sample_weather.json").read_text())
    return s.model_copy(update=update)


def _result(s: Scenario, arrival: int, gate: str, rule_id: str):
    ev = rules.evaluate(s, Proposal(arrival_min=arrival, runway="27R", gate=gate, rationale=""))
    return next((r for r in ev.results if r.rule_id == rule_id), None)


def test_rules_are_off_when_the_scenario_does_not_set_them():
    s = _scenario()
    assert _result(s, 40, "B12", "ground.gate_change_notice") is None
    assert _result(s, 40, "B12", "pilot.flight_crew_duty") is None


def test_gate_change_needs_twenty_minutes_notice():
    s = _scenario(assigned_gate="B14")
    assert _result(s, 19, "B12", "ground.gate_change_notice").passed is False
    assert _result(s, 20, "B12", "ground.gate_change_notice").passed is True
    assert _result(s, 10, "B14", "ground.gate_change_notice") is None  # staying on the assigned gate


def test_flight_crew_duty_blocks_landing_after_it_runs_out():
    s = _scenario(flight_crew_duty_left_min=45)
    assert _result(s, 45, "B12", "pilot.flight_crew_duty").passed is True
    assert _result(s, 46, "B12", "pilot.flight_crew_duty").passed is False
