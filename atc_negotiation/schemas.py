"""Typed messages exchanged between agents, plus the scenario and trace models.

All times are minutes relative to the flight's *scheduled* arrival (t = 0).
A positive `arrival_min` is a delay; the aircraft can't arrive before
`Scenario.earliest_arrival_min` because it is already running late inbound.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class AircraftCategory(str, Enum):
    LIGHT = "L"
    MEDIUM = "M"
    HEAVY = "H"


class RunwayArrival(BaseModel):
    """Another aircraft already slotted on a runway."""

    time_min: int
    category: AircraftCategory


class Runway(BaseModel):
    name: str
    open: bool = True
    taxiway_blocked: bool = False
    arrivals: list[RunwayArrival] = Field(default_factory=list)


class Gate(BaseModel):
    name: str
    free_from_min: int
    free_until_min: int


class Connection(BaseModel):
    passengers: int
    departs_min: int  # when the onward flight leaves, relative to our scheduled arrival
    min_connect_min: int = 35


class MoveEffect(BaseModel):
    """What a move changes in the scenario before the rules run. Exactly one field is set."""

    gate_free_from: dict | None = Field(default=None, description='{"gate": "A1", "free_from_min": 40}')
    crew_shift_ends_min: int | None = None
    fuel_gain_min: int | None = Field(default=None, description=(
        "Extra endurance at arrival from absorbing delay en route (speed reduction) instead of holding"))
    arrival_moved: dict | None = Field(default=None, description='{"runway": "27R", "from_min": 61, "to_min": 75}')
    runway_opens: dict | None = Field(default=None, description='{"runway": "27L", "open_from_min": 70}')


class Move(BaseModel):
    """An option only one organisation holds, e.g. Ground can tow an aircraft off a gate early.

    Each agent's brief lists only its own moves; the others learn of a move when a plan uses it.
    The rule engine applies a plan's moves, then checks every rule as usual: no move relaxes a hard rule."""

    id: str = Field(description="e.g. 'ground.tow_a1'")
    owner: Literal["atc", "pilot", "ground"]
    label: str = Field(description="e.g. 'Tow the aircraft off A1 early'")
    effect: MoveEffect
    cost: float = Field(description="Soft cost, same units as the rule engine's other costs")
    private: bool = True


class AirportInfo(BaseModel):
    """From the organisers' airports.csv. For labels and maps; the rules never read it."""

    iata: str
    name: str
    city: str
    state: str
    country: str
    latitude: float
    longitude: float


class Scenario(BaseModel):
    scenario_id: str
    flight: str
    airline: str
    airline_name: str | None = Field(default=None, description="From airlines.csv, e.g. 'United Air Lines Inc.'")
    origin: str
    destination: str
    origin_info: AirportInfo | None = Field(default=None, description="null if the IATA code is not in airports.csv")
    destination_info: AirportInfo | None = Field(default=None, description="null if the IATA code is not in airports.csv")
    scheduled_arrival_hhmm: str
    disruption: str
    weather_delay_min: int = 0
    late_aircraft_delay_min: int = 0
    earliest_arrival_min: int
    aircraft_category: AircraftCategory = AircraftCategory.MEDIUM
    fuel_endurance_min: int  # flying time left at earliest_arrival_min
    final_reserve_min: int = 30
    connections: list[Connection] = Field(default_factory=list)
    runways: list[Runway]
    gates: list[Gate]
    crew_shift_ends_min: int
    assigned_gate: str | None = Field(default=None, description=(
        "Gate the flight was assigned before the disruption; moving off it needs the workbook's notice"))
    flight_crew_duty_left_min: int | None = Field(default=None, description=(
        "Flight crew duty time left at t=0 under the workbook's 13 h limit; null if not known"))
    turnaround_min: int = 45
    max_arrival_min: int = 180  # beyond this the sector hands the flight to a diversion plan
    moves: list[Move] = Field(default_factory=list, description=(
        "Options each organisation holds privately; a plan may use them via Proposal.moves"))
    source: dict = Field(default_factory=dict)  # raw DOT row, if any
    synthetic_fields: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """One claim an agent relies on, tied to the semantic-model element it comes from."""

    id: int = Field(default=0, description="Citation number. The agent's text refers to it as [id]")
    claim: str = Field(description="Short factual statement, e.g. 'ORD Jan 17-19h weather delay p90 is 0 min'")
    source: str = Field(description=(
        "What backs the claim, as a semantic-model reference: 'metric:<name>' (queried this action), "
        "'rule:<id>', 'passage:<id>', 'code:<CodeSet>.<value>', 'scenario:<field>', or 'check_proposal'"))
    grounded: bool = Field(default=True, description=(
        "False when the source does not resolve in the semantic model, or a metric is cited without "
        "having been queried. The UI should flag these"))
    citation: "Citation | None" = Field(default=None, description="What the source says, resolved from the model")
    trust: Literal["high", "medium", "low"] = Field(default="medium", description=(
        "high: regulation/standard, rule engine, code set, or a metric over >= 100 flights. medium: brief-derived "
        "rule, scenario fact, or a smaller sample. low: synthetic scenario field or ungrounded"))


class GuardrailViolation(BaseModel):
    code: Literal["G1", "G2", "G3", "G4", "G5", "G6", "G7"]
    kind: Literal["uncited_sentence", "dangling_marker", "ungrounded_source", "unsupported_number", "off_source",
                  "unsupported_prose", "thin_sample"]
    where: str = Field(description="'proposal rationale', 'summary', 'objection 2', 'response', 'counter' ...")
    evidence_id: int | None = None
    message: str


class GuardrailReport(BaseModel):
    """Result of the citation guardrails on one agent reply."""

    passed: bool
    violations: list[GuardrailViolation] = Field(default_factory=list)
    checked_claims: int = 0
    low_trust: list[int] = Field(default_factory=list, description="Evidence ids with trust 'low'")
    attempts: int = Field(default=1, description="Submits it took; >1 means the agent was sent back")


class Citation(BaseModel):
    """A source resolved from the semantic model, ready to render as a footnote."""

    kind: Literal["metric", "rule", "passage", "code", "scenario", "rule_engine", "unknown"]
    ref: str = Field(description="Model id, e.g. 'pilot.final_reserve_fuel', 'taxi_in', 'easa:cat.op.mpa.181'")
    label: str = Field(description="Short human title, e.g. 'EASA Air OPS CAT.OP.MPA.181(c)(5) Final reserve fuel'")
    text: str = Field(description="What the source says: rule text, passage quote, metric definition")
    url: str | None = None
    passage_id: str | None = Field(default=None, description="Regulation/brief passage behind a rule or metric")


class Proposal(BaseModel):
    arrival_min: int = Field(description="Revised arrival, minutes after scheduled arrival")
    runway: str
    gate: str
    moves: list[str] = Field(default_factory=list, description=(
        "Ids of Scenario.moves this plan relies on. The rule engine applies them before checking"))
    rationale: str = Field(description="One or two sentences, plain language, with [n] citation markers")
    evidence: list[Evidence] = Field(default_factory=list,
                                     description="Claims the plan relies on, each with its model source. Empty "
                                                 "for the deterministic solver")
    guardrail: GuardrailReport | None = Field(default=None, description="Citation guardrail result; null for the solver")


class Verdict(str, Enum):
    ACCEPT = "accept"
    COUNTER = "counter"


class AgentResponse(BaseModel):
    verdict: Verdict
    objections: list[str] = Field(default_factory=list, description="Empty when accepting. Carry [n] markers")
    summary: str = Field(default="", description="One or two sentences on why this verdict, with [n] markers")
    counter: Proposal | None = Field(default=None, description="Required when verdict is counter")
    evidence: list[Evidence] = Field(default_factory=list, description="Claims behind the verdict, with sources")
    guardrail: GuardrailReport | None = None


class RuleResult(BaseModel):
    rule: str
    rule_id: str | None = Field(default=None, description="Semantic-model rule id, e.g. 'atc.wake_separation'")
    domain: Literal["atc", "pilot", "ground"]
    passed: bool
    hard: bool
    detail: str
    cost: float = 0.0


class Evaluation(BaseModel):
    proposal: Proposal
    results: list[RuleResult]

    # Serialised so the frontend never has to re-derive them.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def feasible(self) -> bool:
        return all(r.passed for r in self.results if r.hard)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cost(self) -> float:
        return sum(r.cost for r in self.results)

    @property
    def hard_failures(self) -> list[RuleResult]:
        return [r for r in self.results if r.hard and not r.passed]


class SqlResult(BaseModel):
    columns: list[str]
    rows: list[list[str | int | float | bool | None]]
    truncated: bool = Field(description="True when the query returned more rows than shown")


class ToolCall(BaseModel):
    """One tool an agent ran while working out its proposal or response."""

    turn: int
    agent: Literal["atc", "pilot", "ground"]
    step: int = Field(description="LLM call within this agent's action, from 1")
    tool: Literal["query_metric", "check_proposal", "lookup_concept"]
    input: dict
    output: str = Field(description="What the agent saw, verbatim (long outputs are cut)")
    is_error: bool = False
    duration_ms: float
    sql_result: SqlResult | None = Field(default=None, description="Rows for query_metric, as a table")
    sql: str | None = Field(default=None, description="SQL that ran. For query_metric it is compiled from the model")
    model_refs: list[str] = Field(default_factory=list, description=(
        "Semantic-model elements this call touched, e.g. ['metric:taxi_in', 'type:Flight.DESTINATION_AIRPORT'] "
        "or the rule ids a check_proposal evaluated. Link these to /semantic/lookup"))


class RunStats(BaseModel):
    llm_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    guardrail_checks: int = 0
    guardrail_rejections: int = Field(default=0, description="Replies sent back (or blocked) by the guardrails")


class TurnRecord(BaseModel):
    turn: int
    proposer: str
    proposal: Proposal
    evaluation: Evaluation
    responses: dict[str, AgentResponse]
    counter_evaluations: dict[str, Evaluation]
    vetoed_accepts: list[str] = Field(
        default_factory=list,
        description="Agents that accepted a proposal the rule engine found infeasible",
    )
    tool_calls: list[ToolCall] = Field(default_factory=list, description="Every tool run during this turn, in order")
    guardrail_blocked: list[str] = Field(default_factory=list, description=(
        "Agents whose reply failed the citation guardrails after repairs. Their accept or counter did not count"))


class NegotiationTrace(BaseModel):
    scenario_id: str
    model: str
    started_at: datetime
    duration_s: float
    turns: list[TurnRecord]
    outcome: Literal["consensus", "fallback", "no_legal_option"] = Field(
        description=("consensus: agents agreed on a feasible plan. fallback: no consensus, the deterministic "
                     "solver picked the cheapest feasible plan. no_legal_option: nothing in the window passes "
                     "every hard rule; `final` is the last attempt, NOT a recommendation, and a human must decide."))
    final: Proposal
    final_evaluation: Evaluation
    fallback_reason: str | None = None
    stats: RunStats = Field(default_factory=RunStats)


Evidence.model_rebuild()
