"""The three negotiating agents. Each has its own prompt and its own priorities.

Agents return typed `Proposal` / `AgentResponse` objects via structured
outputs, so the orchestrator never parses free text. `MockAgent` is a
scripted stand-in for tests and offline demos.
"""

from __future__ import annotations

import json
import os
from typing import Protocol

import anthropic

from . import fallback
from .schemas import AgentResponse, Evaluation, Proposal, Scenario, Verdict

DEFAULT_MODEL = os.environ.get("ATC_MODEL", "claude-opus-5-5")

SHARED_RULES = """\
You are one of three agents resolving a flight disruption. The others cover the
domains you do not. Communicate only through the structured response schema.

Facts about the protocol:
- Times are minutes relative to the flight's scheduled arrival. Negative is early.
- A separate rule engine, not you, decides whether a proposal is legal. You will
  be shown its results. Never accept a proposal the engine marked infeasible.
- You may counter with exactly one alternative proposal. Make it concrete.
- Prefer accepting a feasible proposal that is tolerable for your domain over
  countering for a small gain. The negotiation must finish within 3 turns.
- Keep rationale and objections short and factual. No pleasantries.
"""

ROLE_PROMPTS = {
    "atc": """\
Role: Air Traffic Control.
Your priorities: runway wake separation, keeping blocked taxiways out of use,
and maximising sector throughput (least total delay across the sequence).
You open the negotiation by proposing a revised arrival slot, runway and gate.""",
    "pilot": """\
Role: Pilot in command.
Your priorities: never erode final reserve fuel, flight safety, avoid long
holds, and protect passengers' onward connections where that costs nothing
in safety.""",
    "ground": """\
Role: Ground operations.
Your priorities: a gate that is actually free at arrival, avoiding ground-crew
overtime, and keeping the turnaround on time.""",
}


class Agent(Protocol):
    name: str

    def propose(self, s: Scenario, feedback: Evaluation | None) -> Proposal: ...
    def respond(self, s: Scenario, p: Proposal, ev: Evaluation) -> AgentResponse: ...


def _scenario_brief(s: Scenario) -> str:
    return s.model_dump_json(indent=1, exclude={"source", "synthetic_fields"})


def _evaluation_brief(ev: Evaluation) -> str:
    rows = [f"- [{'PASS' if r.passed else 'FAIL'}{' hard' if r.hard else ''}] {r.domain}/{r.rule}: {r.detail}"
            + (f" (cost {r.cost:g})" if r.cost else "") for r in ev.results]
    status = "FEASIBLE" if ev.feasible else "INFEASIBLE"
    return f"Rule engine verdict: {status}, total soft cost {ev.cost:g}\n" + "\n".join(rows)


class LLMAgent:
    def __init__(self, name: str, client: anthropic.Anthropic | None = None, model: str = DEFAULT_MODEL):
        self.name = name
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.system = SHARED_RULES + "\n" + ROLE_PROMPTS[name]

    def _ask(self, prompt: str, schema):
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=4000,
            system=self.system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
        )
        return resp.parsed_output

    def propose(self, s: Scenario, feedback: Evaluation | None) -> Proposal:
        prompt = f"Scenario:\n{_scenario_brief(s)}\n\n"
        if feedback is not None:
            prompt += (f"Your previous proposal was rejected. Rule engine output:\n"
                       f"{_evaluation_brief(feedback)}\n\n")
        prompt += "Propose a revised arrival slot, runway and gate."
        return self._ask(prompt, Proposal)

    def respond(self, s: Scenario, p: Proposal, ev: Evaluation) -> AgentResponse:
        prompt = (f"Scenario:\n{_scenario_brief(s)}\n\n"
                  f"Proposal on the table:\n{p.model_dump_json(indent=1)}\n\n"
                  f"{_evaluation_brief(ev)}\n\n"
                  "Accept, or counter with one alternative.")
        return self._ask(prompt, AgentResponse)


class MockAgent:
    """Scripted agent: ATC opens naively, others counter with the solver's answer."""

    def __init__(self, name: str):
        self.name = name
        self.model = "mock"

    def propose(self, s: Scenario, feedback: Evaluation | None) -> Proposal:
        if feedback is None:
            return Proposal(arrival_min=s.earliest_arrival_min, runway=s.runways[0].name,
                            gate=s.gates[0].name, rationale="Earliest slot, first runway and gate.")
        best = fallback.solve(s)
        return best.proposal if best else Proposal(
            arrival_min=s.earliest_arrival_min, runway=s.runways[0].name, gate=s.gates[0].name,
            rationale="No feasible option found.")

    def respond(self, s: Scenario, p: Proposal, ev: Evaluation) -> AgentResponse:
        own_cost = sum(r.cost for r in ev.results if r.domain == self.name)
        if ev.feasible and own_cost == 0:
            return AgentResponse(verdict=Verdict.ACCEPT)
        best = fallback.solve(s)
        if ev.feasible and best is not None and best.proposal.model_dump(exclude={"rationale"}) == \
                p.model_dump(exclude={"rationale"}):
            return AgentResponse(verdict=Verdict.ACCEPT)  # nothing better exists; don't stall
        reasons = [f"{r.rule}: {r.detail}" for r in ev.results
                   if r.domain == self.name and (not r.passed or r.cost)]
        if not reasons:
            reasons = (["rule engine marked the proposal infeasible; no legal alternative found"]
                       if not ev.feasible and best is None else ["prefer cheaper option"])
        return AgentResponse(verdict=Verdict.COUNTER, objections=reasons,
                             counter=best.proposal if best else None)


def make_agents(mock: bool = False, model: str = DEFAULT_MODEL) -> dict[str, Agent]:
    if mock:
        return {n: MockAgent(n) for n in ROLE_PROMPTS}
    client = anthropic.Anthropic()
    return {n: LLMAgent(n, client=client, model=model) for n in ROLE_PROMPTS}
