"""Operational constraints, as code. The LLM never gets to decide these.

Each domain exposes one function returning a list of RuleResult. Hard rules
make a proposal infeasible when they fail; soft rules only add cost, which
the orchestrator and the fallback solver use to rank feasible proposals.

Numbers are simplified from ICAO Doc 4444 time-based wake separation and
EASA final-reserve fuel rules; see README for what is approximated.
"""

from __future__ import annotations

from .schemas import AircraftCategory as Cat
from .schemas import Evaluation, Proposal, RuleResult, Scenario

# Seconds required between a leading and a trailing arrival on the same runway.
# Keyed (leader, follower). Anything not listed falls back to radar minimum.
WAKE_SEPARATION_S: dict[tuple[Cat, Cat], int] = {
    (Cat.HEAVY, Cat.HEAVY): 96,
    (Cat.HEAVY, Cat.MEDIUM): 120,
    (Cat.HEAVY, Cat.LIGHT): 144,
    (Cat.MEDIUM, Cat.LIGHT): 120,
}
RADAR_MIN_S = 72

DELAY_COST_PER_MIN = 1.0
MISSED_PAX_COST = 2.0
OVERTIME_COST_PER_MIN = 1.5


def atc_rules(s: Scenario, p: Proposal) -> list[RuleResult]:
    out: list[RuleResult] = []
    rwy = next((r for r in s.runways if r.name == p.runway), None)

    if rwy is None:
        out.append(RuleResult(rule="runway_exists", domain="atc", passed=False, hard=True,
                              detail=f"runway {p.runway!r} is not at {s.destination}"))
        return out

    out.append(RuleResult(rule="runway_open", domain="atc", passed=rwy.open, hard=True,
                          detail=f"{rwy.name} is {'open' if rwy.open else 'closed'}"))
    out.append(RuleResult(rule="taxiway_clear", domain="atc", passed=not rwy.taxiway_blocked, hard=True,
                          detail=f"taxiway from {rwy.name} is {'blocked' if rwy.taxiway_blocked else 'clear'}"))

    # Wake separation against every aircraft already on that runway, both directions.
    worst_gap, worst_need, worst_other = None, 0, None
    for other in rwy.arrivals:
        gap_s = abs(p.arrival_min - other.time_min) * 60
        if other.time_min <= p.arrival_min:
            need = WAKE_SEPARATION_S.get((other.category, s.aircraft_category), RADAR_MIN_S)
        else:
            need = WAKE_SEPARATION_S.get((s.aircraft_category, other.category), RADAR_MIN_S)
        if worst_gap is None or gap_s - need < worst_gap - worst_need:
            worst_gap, worst_need, worst_other = gap_s, need, other
    if worst_other is None:
        out.append(RuleResult(rule="wake_separation", domain="atc", passed=True, hard=True,
                              detail=f"no other traffic on {rwy.name}"))
    else:
        ok = worst_gap >= worst_need
        out.append(RuleResult(
            rule="wake_separation", domain="atc", passed=ok, hard=True,
            detail=(f"{worst_gap}s to {worst_other.category.name.lower()} at t={worst_other.time_min}; "
                    f"need {worst_need}s"),
        ))

    within = s.earliest_arrival_min <= p.arrival_min <= s.max_arrival_min
    out.append(RuleResult(
        rule="slot_in_window", domain="atc", passed=within, hard=True,
        detail=f"arrival t={p.arrival_min} must lie in [{s.earliest_arrival_min}, {s.max_arrival_min}]",
    ))
    delay = max(0, p.arrival_min)
    out.append(RuleResult(rule="sector_delay", domain="atc", passed=True, hard=False,
                          detail=f"{delay} min of sector delay", cost=delay * DELAY_COST_PER_MIN))
    return out


def pilot_rules(s: Scenario, p: Proposal) -> list[RuleResult]:
    out: list[RuleResult] = []
    hold = max(0, p.arrival_min - s.earliest_arrival_min)
    remaining = s.fuel_endurance_min - hold
    out.append(RuleResult(
        rule="final_reserve_fuel", domain="pilot", passed=remaining >= s.final_reserve_min, hard=True,
        detail=f"{hold} min hold leaves {remaining} min fuel; final reserve is {s.final_reserve_min} min",
    ))

    missed = sum(c.passengers for c in s.connections
                 if p.arrival_min + c.min_connect_min > c.departs_min)
    out.append(RuleResult(rule="passenger_connections", domain="pilot", passed=True, hard=False,
                          detail=f"{missed} passengers miss onward flights", cost=missed * MISSED_PAX_COST))
    return out


def ground_rules(s: Scenario, p: Proposal) -> list[RuleResult]:
    out: list[RuleResult] = []
    gate = next((g for g in s.gates if g.name == p.gate), None)
    if gate is None:
        out.append(RuleResult(rule="gate_exists", domain="ground", passed=False, hard=True,
                              detail=f"gate {p.gate!r} is not at {s.destination}"))
        return out

    free = gate.free_from_min <= p.arrival_min <= gate.free_until_min
    out.append(RuleResult(
        rule="gate_available", domain="ground", passed=free, hard=True,
        detail=f"gate {gate.name} free t=[{gate.free_from_min}, {gate.free_until_min}], arrival t={p.arrival_min}",
    ))

    overtime = max(0, p.arrival_min + s.turnaround_min - s.crew_shift_ends_min)
    out.append(RuleResult(rule="crew_overtime", domain="ground", passed=True, hard=False,
                          detail=f"{overtime} min of ground-crew overtime",
                          cost=overtime * OVERTIME_COST_PER_MIN))
    return out


def evaluate(s: Scenario, p: Proposal) -> Evaluation:
    return Evaluation(proposal=p, results=atc_rules(s, p) + pilot_rules(s, p) + ground_rules(s, p))
