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
    turnaround_min: int = 45
    max_arrival_min: int = 180  # beyond this the sector hands the flight to a diversion plan
    source: dict = Field(default_factory=dict)  # raw DOT row, if any
    synthetic_fields: list[str] = Field(default_factory=list)


class Proposal(BaseModel):
    arrival_min: int = Field(description="Revised arrival, minutes after scheduled arrival")
    runway: str
    gate: str
    rationale: str = Field(description="One or two sentences, plain language")


class Verdict(str, Enum):
    ACCEPT = "accept"
    COUNTER = "counter"


class AgentResponse(BaseModel):
    verdict: Verdict
    objections: list[str] = Field(default_factory=list, description="Empty when accepting")
    counter: Proposal | None = Field(default=None, description="Required when verdict is counter")


class RuleResult(BaseModel):
    rule: str
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
