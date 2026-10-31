"""The two stage scenarios must keep the shape the demo script relies on.

demo_storm_ua599: the earliest legal slot is not the cheapest plan, so ATC's opening offer
gets a real objection from ground. demo_storm_vx204_divert: nothing is legal, so the system
must decline. If a rule or parameter change breaks either, the demo breaks with it.
"""

from pathlib import Path

import pytest

from atc_negotiation import fallback
from atc_negotiation.rules import evaluate
from atc_negotiation.schemas import Proposal, Scenario

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"


def _load(name: str) -> Scenario:
    return Scenario.model_validate_json((SCENARIOS / f"{name}.json").read_text())


def _feasible(s: Scenario) -> list:
    out = []
    for t in range(s.earliest_arrival_min, s.max_arrival_min + 1):
        for r in s.runways:
            for g in s.gates:
                ev = evaluate(s, Proposal(arrival_min=t, runway=r.name, gate=g.name, rationale=""))
                if ev.feasible:
                    out.append(ev)
    return out


@pytest.fixture
def ua599() -> Scenario:
    return _load("demo_storm_ua599")


def test_ua599_earliest_slot_is_legal_but_not_cheapest(ua599):
    feasible = _feasible(ua599)
    earliest = min(feasible, key=lambda ev: ev.proposal.arrival_min)
    best = fallback.solve(ua599)
    assert earliest.proposal.arrival_min < best.proposal.arrival_min
    assert earliest.cost > best.cost
    # The objection is ground's: the earliest gate is needed again during the turnaround.
    overrun = next(r for r in earliest.results if r.rule_id == "ground.gate_overrun")
    assert overrun.cost > 0


def test_ua599_cheapest_plan_keeps_fuel_and_connections(ua599):
    best = fallback.solve(ua599)
    pilot = {r.rule_id: r for r in best.results if r.domain == "pilot"}
    assert pilot["pilot.final_reserve_fuel"].passed
    assert pilot["pilot.connections"].cost == 0


def test_ua599_opening_slots_fail_on_wake_separation(ua599):
    """The first minutes after earliest arrival are blocked by heavies: the engine says no, with ICAO's number."""
    ev = evaluate(ua599, Proposal(arrival_min=ua599.earliest_arrival_min, runway="27R", gate="C9", rationale=""))
    assert [r.rule_id for r in ev.hard_failures] == ["atc.wake_separation"]


def test_vx204_has_no_legal_option():
    s = _load("demo_storm_vx204_divert")
    assert fallback.solve(s) is None
    assert _feasible(s) == []


@pytest.mark.parametrize("name", ["demo_storm_ua599", "demo_storm_vx204_divert"])
def test_demo_scenarios_keep_the_real_dot_row(name):
    s = _load(name)
    assert s.source["YEAR"] == "2015" and s.source["ARRIVAL_DELAY"]
    assert s.synthetic_fields, "hand-set fields must be labelled"
