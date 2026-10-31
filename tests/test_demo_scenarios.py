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


# ── demo_storm_aa1453_moves: private moves, negotiated across organisations ──

def _best_with(s: Scenario, moves: list[str]):
    best = None
    for t in range(s.earliest_arrival_min, s.max_arrival_min + 1):
        for r in s.runways:
            for g in s.gates:
                ev = evaluate(s, Proposal(arrival_min=t, runway=r.name, gate=g.name, rationale="", moves=moves))
                if ev.feasible and (best is None or ev.cost < best.cost):
                    best = ev
    return best


@pytest.fixture
def aa1453() -> Scenario:
    return _load("demo_storm_aa1453_moves")


def test_aa1453_nothing_legal_on_the_shared_picture(aa1453):
    """The solver sees slot, runway and gate only: it finds nothing. Private options must be negotiated."""
    assert fallback.solve(aa1453) is None
    assert _feasible(aa1453) == []


def test_aa1453_no_single_organisation_can_resolve_it(aa1453):
    import itertools
    for owner in ("atc", "pilot", "ground"):
        own = [m.id for m in aa1453.moves if m.owner == owner]
        for k in range(1, len(own) + 1):
            for combo in itertools.combinations(own, k):
                assert _best_with(aa1453, list(combo)) is None, (owner, combo)


def test_aa1453_ground_and_atc_together_beat_ground_and_pilot(aa1453):
    gp = _best_with(aa1453, ["ground.tow_a1", "pilot.absorb_en_route"])
    ga = _best_with(aa1453, ["ground.tow_a1", "atc.resequence_heavy"])
    assert gp is not None and ga is not None
    assert ga.proposal.arrival_min < gp.proposal.arrival_min and ga.cost < gp.cost
    missed = next(r for r in ga.results if r.rule_id == "pilot.connections")
    assert missed.cost == 0  # every connecting passenger makes it


def test_moves_never_relax_a_safety_rule(aa1453):
    """Absorbing delay en route adds endurance; final reserve itself is still enforced."""
    ev = evaluate(aa1453, Proposal(arrival_min=aa1453.max_arrival_min, runway="27R", gate="A1", rationale="",
                                   moves=["ground.tow_a1", "pilot.absorb_en_route"]))
    assert any(r.rule_id == "pilot.final_reserve_fuel" and not r.passed for r in ev.results)


def test_unknown_move_is_a_hard_fail(aa1453):
    ev = evaluate(aa1453, Proposal(arrival_min=56, runway="27R", gate="A1", rationale="", moves=["ground.teleport"]))
    assert any(r.rule_id == "plan.move_known" and not r.passed for r in ev.results)
    assert not ev.feasible


def test_reopened_runway_only_usable_from_reopen_time(aa1453):
    early = evaluate(aa1453, Proposal(arrival_min=80, runway="27L", gate="A1", rationale="", moves=["atc.reopen_27l"]))
    assert any(r.rule_id == "atc.runway_open" and not r.passed for r in early.results)
