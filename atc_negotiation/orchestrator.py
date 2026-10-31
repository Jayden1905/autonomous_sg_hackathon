"""Round-based negotiation with a hard turn cap and a deterministic fallback.

Turn 1: ATC proposes. The other two respond. If the proposal is feasible and
both accept, consensus. Otherwise the cheapest feasible counter-proposal
becomes the next turn's proposal (its author becomes the proposer). After
`max_turns` without consensus, `fallback.solve` decides.

An ACCEPT on an infeasible proposal is recorded as a veto by the rule engine:
agents cannot agree their way past a hard constraint.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable

from . import fallback
from .agents import Agent
from .rules import evaluate
from .schemas import Evaluation, NegotiationTrace, Proposal, Scenario, TurnRecord, Verdict

# Progress callback: (event_name, payload). Payloads are pydantic models or dicts.
# Event names are the contract in contracts/CONTRACT.md; don't rename casually.
OnEvent = Callable[[str, object], None]


def negotiate(s: Scenario, agents: dict[str, Agent], max_turns: int = 3,
              on_event: OnEvent | None = None) -> NegotiationTrace:
    emit = on_event or (lambda name, payload: None)
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    turns: list[TurnRecord] = []
    model = _model_of(agents)
    emit("started", {"scenario_id": s.scenario_id, "model": model, "max_turns": max_turns})

    proposer = "atc"
    emit("thinking", {"turn": 1, "agent": "atc", "action": "propose"})
    proposal = agents["atc"].propose(s, feedback=None)

    for turn in range(1, max_turns + 1):
        emit("proposal", {"turn": turn, "proposer": proposer, "proposal": proposal})
        ev = evaluate(s, proposal)
        emit("evaluation", {"turn": turn, "evaluation": ev})

        responders = [n for n in agents if n != proposer]
        responses = {}
        counter_evals: dict[str, Evaluation] = {}
        for n in responders:
            emit("thinking", {"turn": turn, "agent": n, "action": "respond"})
            r = agents[n].respond(s, proposal, ev)
            responses[n] = r
            if r.verdict == Verdict.COUNTER and r.counter is not None:
                counter_evals[n] = evaluate(s, r.counter)
            emit("response", {"turn": turn, "agent": n, "response": r,
                              "counter_evaluation": counter_evals.get(n),
                              "vetoed": r.verdict == Verdict.ACCEPT and not ev.feasible})

        vetoed = [n for n, r in responses.items() if r.verdict == Verdict.ACCEPT and not ev.feasible]
        record = TurnRecord(turn=turn, proposer=proposer, proposal=proposal, evaluation=ev,
                            responses=responses, counter_evaluations=counter_evals, vetoed_accepts=vetoed)
        turns.append(record)
        emit("turn_complete", record)

        all_accept = all(r.verdict == Verdict.ACCEPT for r in responses.values())
        if ev.feasible and all_accept:
            trace = NegotiationTrace(
                scenario_id=s.scenario_id, model=model, started_at=started,
                duration_s=time.perf_counter() - t0, turns=turns, outcome="consensus",
                final=proposal, final_evaluation=ev,
            )
            emit("done", trace)
            return trace

        if turn < max_turns:
            proposer, proposal = _next_proposal(s, agents, proposer, ev, counter_evals, turn + 1, emit)

    best = fallback.solve(s)
    if best is None:
        # Nothing in the window passes every hard rule. Hand back the last
        # proposal with its failing rules so a human sees exactly why, and
        # say so explicitly instead of inventing a plan.
        best = evaluate(s, proposal)
        outcome = "no_legal_option"
        reason = (f"no consensus in {max_turns} turns and no option in the window passes every hard rule; "
                  "human decision required (divert, or extend the window)")
    else:
        outcome = "fallback"
        reason = f"no consensus in {max_turns} turns; deterministic solver chose the cheapest feasible option"
    trace = NegotiationTrace(
        scenario_id=s.scenario_id, model=model, started_at=started,
        duration_s=time.perf_counter() - t0, turns=turns, outcome=outcome,
        final=best.proposal, final_evaluation=best, fallback_reason=reason,
    )
    emit("done", trace)
    return trace


def _next_proposal(s: Scenario, agents: dict[str, Agent], proposer: str, ev: Evaluation,
                   counter_evals: dict[str, Evaluation], next_turn: int, emit: OnEvent) -> tuple[str, Proposal]:
    if counter_evals:
        # Feasible counters first, then fewest hard failures, then cost.
        name, best = min(counter_evals.items(),
                         key=lambda kv: (not kv[1].feasible, len(kv[1].hard_failures), kv[1].cost))
        return name, best.proposal
    # Everyone accepted but the engine said no: the proposer must try again.
    emit("thinking", {"turn": next_turn, "agent": proposer, "action": "propose"})
    return proposer, agents[proposer].propose(s, feedback=ev)


def _model_of(agents: dict[str, Agent]) -> str:
    return getattr(next(iter(agents.values())), "model", "unknown")
