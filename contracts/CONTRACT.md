# Frontend contract

Backend: FastAPI on `http://localhost:8000` (`make serve`). CORS is open.
Generated artefacts in this folder, regenerate with `make contracts`:

- `openapi.json`: full schema, source of truth
- `types.ts`: TypeScript types generated from it (`import type { components } from "./types"`)

Times in every payload are **minutes relative to the flight's scheduled
arrival**. `arrival_min: 38` means 38 minutes late. Negative is early.

## Endpoints

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| GET | `/health` | | `Health` | `dot_dataset_available` tells you whether `/dot/scenarios` will work |
| GET | `/scenarios` | | `ScenarioSummary[]` | Hand-written demo scenarios under `scenarios/` |
| GET | `/scenarios/{id}` | | `Scenario` | 404 if unknown |
| GET | `/dot/scenarios?offset=0&limit=20` | | `Scenario[]` | Built from DOT `flights.csv` rows; 404 until the CSV is in `data/` |
| POST | `/evaluate` | `{scenario, proposal}` | `Evaluation` | Rule engine only, instant. Use for what-if sliders |
| POST | `/fallback` | `Scenario` | `{evaluation: Evaluation \| null}` | Deterministic solver only, instant |
| POST | `/negotiate` | `NegotiateRequest` | `NegotiationTrace` | Blocking, 30–90 s with real agents, <1 s with `mock: true` |
| POST | `/negotiate/stream` | `NegotiateRequest` | SSE | Same, streamed. Use this for the live view |

`NegotiateRequest`:

```json
{ "scenario": { ...Scenario }, "mock": false, "max_turns": 3, "model": null }
```

Set `mock: true` while building the UI: scripted agents, no API cost, same
event sequence and shapes. The mock always converges in 2 turns on the sample
scenario.

## SSE stream (`POST /negotiate/stream`)

`EventSource` can't POST, so use `fetch` + `ReadableStream` or a small helper
such as `@microsoft/fetch-event-source`. Each frame is:

```
event: <name>
data: <json>

```

Events arrive in this order per negotiation. Payload types are in
`types.ts` under `components["schemas"]["StreamEvents"]`, one property per
event name.

| Event | Payload type | When | UI hint |
|---|---|---|---|
| `started` | `StartedEvent` | once, first | show model, reset board |
| `thinking` | `ThinkingEvent` | before each LLM call | spinner on `agent`'s card, `action` is `propose` or `respond` |
| `proposal` | `ProposalEvent` | start of each turn | place the proposal in the centre; highlight `proposer` |
| `evaluation` | `EvaluationEvent` | right after `proposal` | render rule checklist: `results[]` with `passed`, `hard`, `detail`, `cost`; badge `feasible` and total `cost` |
| `response` | `ResponseEvent` | once per non-proposing agent | `response.verdict` is `accept` or `counter`; show `objections[]`; if `counter`, show `response.counter` and its `counter_evaluation`. If `vetoed` is true the agent accepted an illegal plan: show a rule-engine veto marker |
| `turn_complete` | `TurnRecord` | end of each turn | append to the log / timeline |
| `done` | `NegotiationTrace` | last | branch on `outcome` (see below); show `final`, `final_evaluation`, `fallback_reason`, `duration_s` |
| `error` | `ErrorEvent` | instead of `done` | show `message`; typical: missing API key |

Sequence for one turn:

```
thinking(proposer)  →  proposal  →  evaluation
   →  thinking(a) → response(a)  →  thinking(b) → response(b)
   →  turn_complete
```

Then either `done`, or the next turn starts. The next proposer is whichever
agent made the cheapest feasible counter; if nobody countered but the plan was
infeasible, the same proposer goes again.

### `done.outcome`

| `outcome` | Meaning | What to render |
|---|---|---|
| `consensus` | Agents agreed on a plan the rule engine passed | `final` as the agreed plan, green |
| `fallback` | No agreement in `max_turns`; deterministic solver picked the cheapest feasible plan | `final` as the plan, amber, with `fallback_reason` |
| `no_legal_option` | **Nothing** in the window passes every hard rule. `final` is the last attempt, **not a recommendation** | A clear "no legal option, human decision required" state. List `final_evaluation.results` where `hard && !passed` so the operator sees exactly which rules fail. Do not render `final` as if it were a plan |

`scenarios/sample_no_legal_option.json` (`GET /scenarios/sample-no-legal-option-ORD`)
exercises the third case: minimum fuel plus a saturated runway. Use it for
that UI state and for the demo's "the system declines" moment.

## Key shapes (abridged, see types.ts for everything)

```ts
type Proposal = { arrival_min: number; runway: string; gate: string; rationale: string };

type RuleResult = {
  rule: string;                       // e.g. "wake_separation", "final_reserve_fuel"
  domain: "atc" | "pilot" | "ground"; // which card owns this rule
  passed: boolean;
  hard: boolean;                      // hard+failed makes the plan infeasible
  detail: string;                     // human sentence, show verbatim
  cost: number;                       // soft rules only
};

type Evaluation = { proposal: Proposal; results: RuleResult[]; feasible: boolean; cost: number };

type AgentResponse = {
  verdict: "accept" | "counter";
  objections: string[];
  counter: Proposal | null;
};

type NegotiationTrace = {
  scenario_id: string; model: string; started_at: string; duration_s: number;
  turns: TurnRecord[];
  outcome: "consensus" | "fallback";
  final: Proposal; final_evaluation: Evaluation;
  fallback_reason: string | null;
};
```

`Scenario` carries everything needed to draw the board: `runways[]` (with
`open`, `taxiway_blocked`, and `arrivals[]` of other traffic by `time_min` and
wake `category` L/M/H), `gates[]` with free windows, `connections[]`,
`fuel_endurance_min`, `final_reserve_min`, `crew_shift_ends_min`.
`synthetic_fields` lists which fields were generated rather than taken from
the DOT data; the judges care, so show it somewhere (tooltip is fine).

### Labels and map data (real, from the organisers' CSVs)

```ts
type AirportInfo = {
  iata: string; name: string; city: string; state: string; country: string;
  latitude: number; longitude: number;
};
// on Scenario:
airline_name: string | null;       // "United Air Lines Inc."; `airline` is still the code "UA"
origin_info: AirportInfo | null;   // null if the IATA code isn't in airports.csv
destination_info: AirportInfo | null;
```

These come from `airports.csv` and `airlines.csv`, so they're real, not
synthetic. Enough for a header ("UA1234 · United · Denver → Chicago O'Hare")
and a map pin or route line. The rules never read them. Both sample scenarios
include them, so `mock` mode exercises the same shapes.

Runway names are synthetic and vary per scenario (`09L/09R`, `27L/27R`, …);
read them from `runways[].name`, never hardcode.

## Rule names

| `rule` | domain | hard | meaning |
|---|---|---|---|
| `runway_exists` | atc | yes | runway name not at this airport |
| `runway_open` | atc | yes | runway closed |
| `taxiway_clear` | atc | yes | exit taxiway blocked |
| `wake_separation` | atc | yes | too close to another arrival on that runway |
| `slot_in_window` | atc | yes | outside `[earliest_arrival_min, max_arrival_min]` |
| `sector_delay` | atc | no | cost = delay minutes |
| `final_reserve_fuel` | pilot | yes | holding would eat into final reserve |
| `passenger_connections` | pilot | no | cost = 2 × passengers missing onward flights |
| `gate_exists` | ground | yes | gate name not at this airport |
| `gate_available` | ground | yes | gate not free at arrival time |
| `crew_overtime` | ground | no | cost = 1.5 × overtime minutes |

## Minimal client

```ts
import { fetchEventSource } from "@microsoft/fetch-event-source";
import type { components } from "./types";
type S = components["schemas"];

await fetchEventSource("http://localhost:8000/negotiate/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ scenario, mock: true, max_turns: 3 } satisfies S["NegotiateRequest"]),
  onmessage(ev) {
    switch (ev.event as keyof S["StreamEvents"]) {
      case "evaluation": { const p: S["EvaluationEvent"] = JSON.parse(ev.data); break; }
      case "done":       { const t: S["NegotiationTrace"] = JSON.parse(ev.data); break; }
      // ...
    }
  },
});
```
