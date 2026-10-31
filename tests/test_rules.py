import json
from pathlib import Path

import pytest

from atc_negotiation import fallback
from atc_negotiation.rules import evaluate
from atc_negotiation.schemas import Proposal, Scenario

SAMPLE = Path(__file__).parent.parent / "scenarios" / "sample_weather.json"


@pytest.fixture
def scenario() -> Scenario:
    return Scenario.model_validate_json(SAMPLE.read_text())


def _fails(ev, rule):
    return any(r.rule == rule and not r.passed for r in ev.results)


def test_closed_runway_is_hard_fail(scenario):
    ev = evaluate(scenario, Proposal(arrival_min=50, runway="27L", gate="B12", rationale=""))
    assert not ev.feasible and _fails(ev, "runway_open")


def test_wake_separation_behind_heavy(scenario):
    # Heavy lands at t=31; a medium one minute later has 60 s, needs 120 s.
    ev = evaluate(scenario, Proposal(arrival_min=32, runway="27R", gate="B14", rationale=""))
    assert _fails(ev, "wake_separation")


def test_fuel_reserve_blocks_long_hold(scenario):
    # 55 min endurance, 30 min reserve: a hold over 25 min is illegal.
    ev = evaluate(scenario, Proposal(arrival_min=22 + 26, runway="27R", gate="B12", rationale=""))
    assert _fails(ev, "final_reserve_fuel")
    ev = evaluate(scenario, Proposal(arrival_min=22 + 25, runway="27R", gate="B12", rationale=""))
    assert not _fails(ev, "final_reserve_fuel")


def test_gate_window(scenario):
    ev = evaluate(scenario, Proposal(arrival_min=33, runway="27R", gate="B14", rationale=""))
    assert _fails(ev, "gate_available")


def test_soft_costs_do_not_block(scenario):
    ev = evaluate(scenario, Proposal(arrival_min=44, runway="27R", gate="B12", rationale=""))
    assert ev.feasible
    assert ev.cost > 0


def test_fallback_is_feasible_and_deterministic(scenario):
    a, b = fallback.solve(scenario), fallback.solve(scenario)
    assert a is not None and a.feasible
    assert a.proposal == b.proposal


def test_fallback_returns_none_when_nothing_fits(scenario):
    scenario.fuel_endurance_min = scenario.final_reserve_min  # zero holding allowed
    scenario.runways[1].arrivals.append(type(scenario.runways[1].arrivals[0])(time_min=22, category="H"))
    assert fallback.solve(scenario) is None
