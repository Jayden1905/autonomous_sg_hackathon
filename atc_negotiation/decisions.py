"""Human approval of a negotiated plan, then (simulated) execution, with an audit trail.

The agents negotiate without human intervention until consensus (the brief). Nothing is
executed until a named operator approves. Approval re-runs the rule engine first, against
the scenario as it stands now if the caller sends an updated one: a plan that was legal
when agreed may not be legal any more, and the engine has the last word, not the operator.

A `no_legal_option` outcome cannot be approved: `final` is the last attempt, not a plan.
The operator can only divert or reject it.

Execution is simulated: approving records the instructions that would be issued (slot,
runway, gate), it does not send them anywhere. Every record says so.

Decisions live in memory and every change is appended to traces/decisions.jsonl, which is
replayed at import so a server reload keeps them.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .rules import evaluate
from .schemas import Evaluation, NegotiationTrace, Proposal, Scenario

LOG = Path(__file__).resolve().parent.parent / "traces" / "decisions.jsonl"

Status = Literal["pending_approval", "needs_human_decision", "executed", "rejected", "diverted"]
Action = Literal["approve", "reject", "divert"]
SIMULATED = "simulated: recorded here, not sent to any real ATC, airline or ground system"


class AuditEntry(BaseModel):
    at: datetime
    by: str = Field(description="'system' or the operator's name")
    event: str = Field(description="created | approve | reject | divert | approve_refused")
    note: str = ""


class ExecutedAction(BaseModel):
    kind: Literal["slot_assigned", "gate_assigned", "hold_issued", "divert_issued"]
    detail: str


class Decision(BaseModel):
    decision_id: str
    scenario_id: str
    flight: str
    status: Status
    outcome: Literal["consensus", "fallback", "no_legal_option"]
    plan: Proposal = Field(description="The plan put to the operator (trace.final)")
    evaluation: Evaluation = Field(description="Rule engine verdict, re-run at approval")
    allowed_actions: list[Action]
    executed: list[ExecutedAction] = Field(default_factory=list,
                                           description=f"Instructions issued on approval or divert. {SIMULATED}")
    simulated: bool = True
    audit: list[AuditEntry]
    scenario: Scenario
    trace: NegotiationTrace


class CreateDecision(BaseModel):
    scenario: Scenario
    # Untyped on purpose: typing it as NegotiationTrace would make FastAPI split NegotiationTrace,
    # Evaluation, TurnRecord and AgentResponse into -Input/-Output schemas and rename the FE's types.
    trace: dict[str, Any] = Field(description=(
        "A NegotiationTrace: the `done` payload of /negotiate/stream, or /negotiate's response, unchanged"))


class DecideRequest(BaseModel):
    action: Action
    operator: str = Field(min_length=1, description="Who decided. Goes into the audit trail")
    note: str = ""
    scenario: Scenario | None = Field(default=None, description=(
        "approve only: the situation as it stands now. The plan is re-checked against it; omit to re-check "
        "against the scenario it was negotiated on"))


class ApproveRefused(BaseModel):
    detail: str
    evaluation: Evaluation


_lock = threading.Lock()
_decisions: dict[str, Decision] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _allowed(status: Status) -> list[Action]:
    return {"pending_approval": ["approve", "reject"],
            "needs_human_decision": ["divert", "reject"]}.get(status, [])


def _save(d: Decision) -> None:
    _decisions[d.decision_id] = d
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        f.write(d.model_dump_json() + "\n")


def _replay() -> None:
    if not LOG.exists():
        return
    for line in LOG.read_text().splitlines():
        try:
            d = Decision.model_validate_json(line)
        except ValueError:
            continue  # a record from an older schema; skip rather than fail the server
        _decisions[d.decision_id] = d


def _instructions(s: Scenario, p: Proposal) -> list[ExecutedAction]:
    hold = max(0, p.arrival_min - s.earliest_arrival_min)
    out = [ExecutedAction(kind="slot_assigned",
                          detail=f"{s.flight} cleared to land runway {p.runway} at t+{p.arrival_min} min")]
    if hold:
        out.append(ExecutedAction(kind="hold_issued", detail=f"{s.flight} holds {hold} min before approach"))
    out.append(ExecutedAction(kind="gate_assigned", detail=f"gate {p.gate} reserved for {s.flight}"))
    return out


def create(req: CreateDecision) -> Decision:
    try:
        t = NegotiationTrace.model_validate(req.trace)
    except ValueError as e:
        raise HTTPException(422, f"trace is not a NegotiationTrace: {e}") from e
    if t.scenario_id != req.scenario.scenario_id:
        raise HTTPException(422, f"trace is for {t.scenario_id!r}, scenario is {req.scenario.scenario_id!r}")
    status: Status = "needs_human_decision" if t.outcome == "no_legal_option" else "pending_approval"
    note = ("no plan passes every hard rule; divert or reject" if status == "needs_human_decision"
            else f"{t.outcome}: awaiting operator approval")
    d = Decision(decision_id=uuid.uuid4().hex[:12], scenario_id=t.scenario_id, flight=req.scenario.flight,
                 status=status, outcome=t.outcome, plan=t.final, evaluation=t.final_evaluation,
                 allowed_actions=_allowed(status), scenario=req.scenario, trace=t,
                 audit=[AuditEntry(at=_now(), by="system", event="created", note=note)])
    with _lock:
        _save(d)
    return d


def decide(decision_id: str, req: DecideRequest) -> Decision:
    with _lock:
        d = _decisions.get(decision_id)
        if d is None:
            raise HTTPException(404, f"no decision {decision_id!r}")
        if req.action not in d.allowed_actions:
            raise HTTPException(409, f"{req.action!r} is not allowed when status is {d.status!r}; "
                                     f"allowed: {d.allowed_actions}")
        d = d.model_copy(deep=True)
        entry = AuditEntry(at=_now(), by=req.operator, event=req.action, note=req.note)

        if req.action == "approve":
            scenario = req.scenario or d.scenario
            ev = evaluate(scenario, d.plan)
            if not ev.feasible:
                fails = "; ".join(f"{r.rule}: {r.detail}" for r in ev.hard_failures)
                d.evaluation = ev
                d.audit.append(AuditEntry(at=_now(), by=req.operator, event="approve_refused",
                                          note=f"rule engine re-check failed: {fails}"))
                _save(d)
                raise HTTPException(409, ApproveRefused(
                    detail=f"plan no longer passes every hard rule: {fails}", evaluation=ev).model_dump(mode="json"))
            d.scenario, d.evaluation = scenario, ev
            d.status, d.executed = "executed", _instructions(scenario, d.plan)
        elif req.action == "divert":
            d.status = "diverted"
            d.executed = [ExecutedAction(kind="divert_issued",
                                         detail=f"{d.flight} diverts" + (f": {req.note}" if req.note else ""))]
        else:
            d.status = "rejected"

        d.audit.append(entry)
        d.allowed_actions = _allowed(d.status)
        _save(d)
        return d


decisions_router = APIRouter(prefix="/decisions", tags=["human approval"])


@decisions_router.post("", response_model=Decision, status_code=201)
def create_decision(req: CreateDecision) -> Decision:
    """Put a finished negotiation in front of an operator. Call it with the stream's `done` trace."""
    return create(req)


@decisions_router.get("", response_model=list[Decision])
def list_decisions(status: Status | None = None) -> list[Decision]:
    """Newest first. Filter with ?status=pending_approval for the operator's queue."""
    ds = sorted(_decisions.values(), key=lambda d: d.audit[0].at, reverse=True)
    return [d for d in ds if status is None or d.status == status]


@decisions_router.get("/{decision_id}", response_model=Decision)
def get_decision(decision_id: str) -> Decision:
    d = _decisions.get(decision_id)
    if d is None:
        raise HTTPException(404, f"no decision {decision_id!r}")
    return d


@decisions_router.post("/{decision_id}/decide", response_model=Decision,
                       responses={409: {"model": ApproveRefused,
                                        "description": "Action not allowed in this status, or the rule engine "
                                                       "re-check failed (body carries the evaluation)"}})
def decide_endpoint(decision_id: str, req: DecideRequest) -> Decision:
    """approve: re-check, then record the (simulated) instructions. reject: close it. divert: no-legal-option only."""
    return decide(decision_id, req)


_replay()
