"""HTTP API for the React frontend. Contract: contracts/CONTRACT.md.

Run with `make serve` (uvicorn on :8000). OpenAPI at /openapi.json, docs at /docs.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import data, fallback
from .agents import DEFAULT_EFFORT, DEFAULT_MODEL, make_agents
from .orchestrator import negotiate
from .rules import evaluate
from .semantic_api import semantic_router
from .schemas import Evaluation, GuardrailReport, NegotiationTrace, Proposal, Scenario, ToolCall
from .sqlengine import dataset_available

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "scenarios"
DOT_CSV = ROOT / "data" / "flights.csv"

EventName = Literal["started", "thinking", "tool_call", "guardrail", "proposal", "evaluation", "response",
                    "turn_complete", "done", "error"]

app = FastAPI(
    title="ATC negotiation API",
    version="0.1.0",
    description="Three-agent (ATC / Pilot / Ground) disruption negotiation. See contracts/CONTRACT.md.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(semantic_router)


# ---- request / response models -------------------------------------------------

class Health(BaseModel):
    status: Literal["ok"]
    default_model: str
    default_effort: str
    dot_dataset_available: bool = Field(description="flights.csv present: /dot/scenarios works")
    sql_tool_available: bool = Field(description="all three CSVs present: agents can call query_metric")


class ScenarioSummary(BaseModel):
    scenario_id: str
    flight: str
    origin: str
    destination: str
    disruption: str
    earliest_arrival_min: int


class NegotiateRequest(BaseModel):
    scenario: Scenario
    mock: bool = Field(default=False, description="Scripted agents, no LLM calls. For UI development.")
    max_turns: int = Field(default=3, ge=1, le=6)
    model: str | None = Field(default=None, description="Overrides the server default model")
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = Field(
        default=None, description="Reasoning effort per agent call. Higher is slower. Default: server setting")


class EvaluateRequest(BaseModel):
    scenario: Scenario
    proposal: Proposal


class FallbackResponse(BaseModel):
    evaluation: Evaluation | None = Field(description="null when no option in the window passes every hard rule")


class ThinkingEvent(BaseModel):
    turn: int
    agent: Literal["atc", "pilot", "ground"]
    action: Literal["propose", "respond"]


class GuardrailEvent(BaseModel):
    turn: int
    agent: Literal["atc", "pilot", "ground"]
    report: GuardrailReport = Field(description="passed=false: the reply was sent back to the agent with these "
                                                "violations (or, after the last repair, blocked)")


class StartedEvent(BaseModel):
    scenario_id: str
    model: str
    max_turns: int


class ProposalEvent(BaseModel):
    turn: int
    proposer: Literal["atc", "pilot", "ground"]
    proposal: Proposal


class EvaluationEvent(BaseModel):
    turn: int
    evaluation: Evaluation


class ResponseEvent(BaseModel):
    turn: int
    agent: Literal["atc", "pilot", "ground"]
    response: "AgentResponse"
    counter_evaluation: Evaluation | None
    vetoed: bool = Field(description="True when the agent accepted a proposal the rule engine found infeasible")


class ErrorEvent(BaseModel):
    message: str
    type: str


class StreamEvents(BaseModel):
    """Not an endpoint. Exists so every SSE payload type lands in the OpenAPI schema."""

    started: StartedEvent
    thinking: ThinkingEvent
    tool_call: ToolCall
    guardrail: GuardrailEvent
    proposal: ProposalEvent
    evaluation: EvaluationEvent
    response: ResponseEvent
    turn_complete: "TurnRecord"
    done: NegotiationTrace
    error: ErrorEvent


from .schemas import AgentResponse, TurnRecord  # noqa: E402  (forward refs above)

ResponseEvent.model_rebuild()
StreamEvents.model_rebuild()


# ---- endpoints -----------------------------------------------------------------

@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", default_model=DEFAULT_MODEL, default_effort=DEFAULT_EFFORT,
                  dot_dataset_available=DOT_CSV.exists(), sql_tool_available=dataset_available())


@app.get("/scenarios", response_model=list[ScenarioSummary])
def list_scenarios() -> list[ScenarioSummary]:
    out = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        s = Scenario.model_validate_json(path.read_text())
        out.append(ScenarioSummary(**s.model_dump(include=set(ScenarioSummary.model_fields))))
    return out


@app.get("/scenarios/{scenario_id}", response_model=Scenario)
def get_scenario(scenario_id: str) -> Scenario:
    for path in SCENARIO_DIR.glob("*.json"):
        s = Scenario.model_validate_json(path.read_text())
        if s.scenario_id == scenario_id:
            return s
    raise HTTPException(404, f"no scenario {scenario_id!r}")


@app.get("/dot/scenarios", response_model=list[Scenario])
def dot_scenarios(offset: int = 0, limit: int = 20) -> list[Scenario]:
    """Scenarios built from qualifying rows of the DOT 2015 flights.csv."""
    if not DOT_CSV.exists():
        raise HTTPException(404, f"DOT dataset not found at {DOT_CSV.relative_to(ROOT)}")
    rows = list(data.qualifying_rows(DOT_CSV, limit=offset + limit))[offset:]
    return [data.scenario_from_row(r) for r in rows]


@app.post("/evaluate", response_model=Evaluation)
def evaluate_proposal(req: EvaluateRequest) -> Evaluation:
    """Rule engine only. Use for what-if sliders: no LLM involved."""
    return evaluate(req.scenario, req.proposal)


@app.post("/fallback", response_model=FallbackResponse)
def run_fallback(scenario: Scenario) -> FallbackResponse:
    """Deterministic solver only."""
    return FallbackResponse(evaluation=fallback.solve(scenario))


@app.post("/negotiate", response_model=NegotiationTrace)
def run_negotiation(req: NegotiateRequest) -> NegotiationTrace:
    """Blocking. Returns the full trace once done (1-4 min with real agents)."""
    agents = make_agents(mock=req.mock, model=req.model or DEFAULT_MODEL, effort=req.effort or DEFAULT_EFFORT)
    return negotiate(req.scenario, agents, max_turns=req.max_turns)


@app.post("/negotiate/stream", response_class=StreamingResponse,
          responses={200: {"content": {"text/event-stream": {}},
                           "description": "SSE stream. Event names and payloads: StreamEvents schema."}})
async def stream_negotiation(req: NegotiateRequest):
    """Same as /negotiate but streams one SSE event per step. Ends with `done` or `error`."""
    q: queue.Queue[tuple[str, object] | None] = queue.Queue()

    def worker() -> None:
        try:
            agents = make_agents(mock=req.mock, model=req.model or DEFAULT_MODEL,
                                 effort=req.effort or DEFAULT_EFFORT)
            negotiate(req.scenario, agents, max_turns=req.max_turns,
                      on_event=lambda name, payload: q.put((name, payload)))
        except Exception as e:  # noqa: BLE001  surfaced to the client as an event
            q.put(("error", {"message": str(e), "type": type(e).__name__}))
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()
    loop = asyncio.get_running_loop()

    async def gen():
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is None:
                return
            name, payload = item
            yield f"event: {name}\ndata: {json.dumps(_jsonable(payload))}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/_schemas/stream-events", response_model=StreamEvents, include_in_schema=True,
         summary="Schema anchor for SSE payloads; never call this")
def _stream_events_schema() -> StreamEvents:  # pragma: no cover
    raise HTTPException(404, "schema anchor only")


def _jsonable(obj: object) -> object:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj
