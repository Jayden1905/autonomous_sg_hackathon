"""Deterministic, LLM-free resolution. Used when the agents fail to converge.

Enumerates every (arrival minute, runway, gate) in the window, drops anything
that fails a hard rule, and returns the cheapest feasible option. Ties go to
the earliest arrival. Same input always gives the same output.
"""

from __future__ import annotations

from .rules import evaluate
from .schemas import Evaluation, Proposal, Scenario


def solve(s: Scenario) -> Evaluation | None:
    best: Evaluation | None = None
    for t in range(s.earliest_arrival_min, s.max_arrival_min + 1):
        for rwy in s.runways:
            for gate in s.gates:
                ev = evaluate(s, Proposal(
                    arrival_min=t, runway=rwy.name, gate=gate.name,
                    rationale="Deterministic fallback: cheapest option that passes every hard rule.",
                ))
                if not ev.feasible:
                    continue
                if best is None or ev.cost < best.cost:
                    best = ev
    return best
