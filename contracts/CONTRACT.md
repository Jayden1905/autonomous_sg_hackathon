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
| GET | `/health` | | `Health` | `dot_dataset_available`: `/dot/scenarios` works. `sql_tool_available`: agents can call `query_metric` |
| GET | `/scenarios` | | `ScenarioSummary[]` | Hand-written demo scenarios under `scenarios/` |
| GET | `/scenarios/{id}` | | `Scenario` | 404 if unknown |
| GET | `/dot/scenarios?offset=0&limit=20` | | `Scenario[]` | Built from DOT `flights.csv` rows; 404 until the CSV is in `data/` |
| POST | `/evaluate` | `{scenario, proposal}` | `Evaluation` | Rule engine only, instant. Use for what-if sliders |
| POST | `/fallback` | `Scenario` | `{evaluation: Evaluation \| null}` | Deterministic solver only, instant |
| POST | `/negotiate` | `NegotiateRequest` | `NegotiationTrace` | Blocking, 20–90 s with real agents at `effort: "low"` (longer at higher effort), <1 s with `mock: true` |
| POST | `/negotiate/stream` | `NegotiateRequest` | SSE | Same, streamed. Use this for the live view |
| GET | `/semantic/graph`, `/semantic/model`, `/semantic/brief/{role}`, `/semantic/lookup?term=` | | JSON | Read-only semantic model the agents are grounded in. `/semantic/` (not in OpenAPI) is a ready-made HTML viewer. Use `/semantic/lookup?term={rule_id}` to explain a rule result |

`NegotiateRequest`:

```json
{ "scenario": { ...Scenario }, "mock": false, "max_turns": 3, "model": null, "effort": null }
```

`effort` is `low | medium | high | xhigh | max` or null for the server default
(`Health.default_effort`, `low`). Higher means more reasoning per agent call and
a slower negotiation.

## How an agent decides (why there is a `tool_call` event)

Each agent action (propose, or respond) is a tool-calling loop, up to 6 LLM
calls. Every tool goes through the **semantic model** (`/semantic/*`); agents
never write SQL:

| `tool` | `input` | What it does |
|---|---|---|
| `query_metric` | `{metric, filters, group_by}` | Historical stats (n, avg, median, p90, max) for one **model metric** (e.g. `taxi_in`, `weather_delay_min`) over the real 2015 DOT flights, filtered by model dimensions (`destination`, `month`, `arrival_hour`, ...; unused ones are `null`). The SQL is compiled from the model and returned in `sql`. `sql_result` has `columns`/`rows` for a table view |
| `check_proposal` | `{arrival_min, runway, gate}` | Runs the rule engine on a draft plan. `output` lists each result by model rule id and source passage |
| `lookup_concept` | `{term}` | The model's definition of a term, rule id, code or passage |

Every call is streamed as a `tool_call` event and kept in `TurnRecord.tool_calls`.
`model_refs` lists the model elements the call touched (`metric:taxi_in`,
`type:Flight.DESTINATION_AIRPORT`, `rule:atc.wake_separation`); render them as
chips that open `/semantic/lookup?term=<part after the colon>`.

### Evidence (why a plan is trustworthy)

Plans and responses carry `evidence: Evidence[]`:

```ts
type Evidence = {
  id: number;        // citation number; the agent's text refers to it as [id]
  claim: string;     // "JFK Jan 21h taxi_in median 7, p90 13 min (n=72)"
  source: string;    // "metric:taxi_in" | "rule:<id>" | "passage:<id>" | "code:<Set>.<value>"
                     // | "scenario:<field>" | "check_proposal"
  grounded: boolean; // false = source not in the model, or a metric cited without being queried
  citation: Citation | null;
  trust: "high" | "medium" | "low"; // high: regulation, rule engine, code set, metric over >= 100 flights
                                    // medium: brief-derived rule, scenario fact, smaller sample
                                    // low: synthetic scenario field, or ungrounded
};

type Citation = {    // resolved from the semantic model; render as the footnote
  kind: "metric" | "rule" | "passage" | "code" | "scenario" | "rule_engine" | "unknown";
  ref: string;       // "pilot.final_reserve_fuel"
  label: string;     // "Rule pilot.final_reserve_fuel (hard), EASA Air OPS ..., CAT.OP.MPA.181(c)(5) ..."
  text: string;      // what the source says: rule text, passage quote, metric definition
  url: string | null;
  passage_id: string | null; // regulation/brief passage behind a rule or metric
};
```

### Citation guardrails

Every agent reply passes deterministic checks in code (no LLM) before anyone sees it:

| Code | Rejects when |
|---|---|
| G1 | a sentence in rationale / summary / objection has no `[n]` marker |
| G2 | a marker points at no evidence item |
| G3 | a source is not in the semantic model, or a metric is cited without being queried in that action |
| G4 | a number in a claim is not in its cited source (only "plan time ± a sourced duration" is allowed as arithmetic) |
| G5 | a number is real but came from a different source than the one cited |
| G6 | a number in a sentence is not in the evidence that sentence cites |
| G7 | a metric claim rests on fewer than 10 flights |

A failing reply is sent back to the agent with the violations (up to 2 times).
If it still fails, `Proposal.guardrail` / `AgentResponse.guardrail` has
`passed: false`, the agent is listed in `TurnRecord.guardrail_blocked`, and
its reply **does not count**: an accept isn't an accept, a counter can't become
the next proposal. Show those replies as "blocked: uncited claims".
`stats.guardrail_checks` / `guardrail_rejections` give totals for the run.

### Citations in agent replies

Every agent reply is cited like a paper. `Proposal.rationale`,
`AgentResponse.summary` and each `AgentResponse.objections[i]` contain markers
like `[1]` or `[2][3]` (also `[2, 3]`), and each number is an `Evidence.id` in
the **same object's** `evidence` list (a counter's rationale cites
`counter.evidence`). The backend rejects prose without markers or with markers
that point at nothing, so every marker you receive resolves.

Render: replace each `[n]` with a superscript link; hover or click shows
`evidence[n-1].claim` and `citation.label` / `citation.text`, with
`citation.url` as "open source". List the evidence underneath as footnotes.
Regex for markers: `/\[(\d+(?:\s*,\s*\d+)*)\]/g`.

Example from a real run (ATC proposal):

> Hour-17 ORD weather delay p90 is 16 min, falling to 5 at hour 18 ... so a +38 slot fits the usual clearing [4][5].
>
> [4] ORD weather_delay_min p90 16 at hour 17, 5 at hour 18 · *Metric weather_delay_min (min), 2015 US DOT on-time data*
> [2] Wake minima M>L 180 s, H>M 120 s · *Rule atc.wake_separation (hard), ICAO Doc 4444 PANS-ATM §5.8.2*

The backend checks every citation against the semantic model and against what
that agent actually queried in that action. An agent that cites something
ungrounded is sent back once to fix it; if it still doesn't, the claim is kept
with `grounded: false`. **Show `grounded: false` as "unverified"** (e.g. grey,
struck, or a warning icon), never as a normal claim. Show evidence under the
rationale with the source as a chip.

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
| `thinking` | `ThinkingEvent` | an agent starts an action | spinner on `agent`'s card, `action` is `propose` or `respond` |
| `guardrail` | `GuardrailEvent` | each time an agent submits, 1..3 per action | `report.passed` false = the reply was **rejected** and sent back with `report.violations` (show a red "citation check failed: G6 ..." line on the agent's card); true = it passed. `report.attempts` counts submits |
| `tool_call` | `ToolCall` | each tool the agent runs, 0..n per action | append to `agent`'s card as an activity line: `tool` + short `input` (the SQL, the draft plan, the term). Expandable: `output`, or `sql_result` as a table. Red if `is_error` (the agent sees the error and retries) |
| `proposal` | `ProposalEvent` | start of each turn | place the proposal in the centre; highlight `proposer` |
| `evaluation` | `EvaluationEvent` | right after `proposal` | render rule checklist: `results[]` with `passed`, `hard`, `detail`, `cost`; badge `feasible` and total `cost` |
| `response` | `ResponseEvent` | once per non-proposing agent | `response.verdict` is `accept` or `counter`; show `objections[]`; if `counter`, show `response.counter` and its `counter_evaluation`. If `vetoed` is true the agent accepted an illegal plan: show a rule-engine veto marker |
| `turn_complete` | `TurnRecord` | end of each turn | append to the log / timeline |
| `done` | `NegotiationTrace` | last | branch on `outcome` (see below); show `final`, `final_evaluation`, `fallback_reason`, `duration_s` |
| `error` | `ErrorEvent` | instead of `done` | show `message`; typical: missing API key |

Sequence for one turn:

```
thinking(proposer) → tool_call* → proposal → evaluation
   → thinking(a) → tool_call* → response(a)
   → thinking(b) → tool_call* → response(b)
   → turn_complete
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
type Proposal = {
  arrival_min: number; runway: string; gate: string; rationale: string;
  evidence: Evidence[];               // see "Evidence" above; empty for the deterministic solver
};

type ToolCall = {
  turn: number; agent: "atc" | "pilot" | "ground"; step: number;
  tool: "query_metric" | "check_proposal" | "lookup_concept";
  input: Record<string, unknown>;     // {metric, filters, group_by} | {arrival_min, runway, gate} | {term}
  output: string;                     // what the agent saw, cut at 4000 chars
  is_error: boolean; duration_ms: number;
  sql_result: { columns: string[]; rows: unknown[][]; truncated: boolean } | null;
  sql: string | null;                 // query_metric only: SQL compiled from the model
  model_refs: string[];               // semantic-model elements touched
};

type RuleResult = {
  rule: string;                       // e.g. "wake_separation", "final_reserve_fuel"
  rule_id: string | null;             // semantic-model id, e.g. "atc.wake_separation"
  domain: "atc" | "pilot" | "ground"; // which card owns this rule
  passed: boolean;
  hard: boolean;                      // hard+failed makes the plan infeasible
  detail: string;                     // human sentence, show verbatim
  cost: number;                       // soft rules only
};

type Evaluation = { proposal: Proposal; results: RuleResult[]; feasible: boolean; cost: number };

type AgentResponse = {
  verdict: "accept" | "counter";
  summary: string;                    // why this verdict, with [n] markers
  objections: string[];               // each with [n] markers
  counter: Proposal | null;
  evidence: Evidence[];
  guardrail: GuardrailReport | null;  // also on Proposal
};

type GuardrailReport = {
  passed: boolean; attempts: number; checked_claims: number;
  low_trust: number[];                // evidence ids with trust "low"
  violations: { code: "G1".."G7"; kind: string; where: string; evidence_id: number | null; message: string }[];
};

type NegotiationTrace = {
  scenario_id: string; model: string; started_at: string; duration_s: number;
  turns: TurnRecord[];
  outcome: "consensus" | "fallback" | "no_legal_option";
  final: Proposal; final_evaluation: Evaluation;
  fallback_reason: string | null;
  stats: { llm_calls: number; tool_calls: number; input_tokens: number; output_tokens: number;
           cache_read_tokens: number };
};
// TurnRecord also carries tool_calls: ToolCall[] for that turn.
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

**Key the UI on `rule_id`**, not `rule`: ids are stable semantic-model ids that
`/semantic/lookup?term=<rule_id>` explains; `rule` is a display label and may
carry a suffix such as ` (operator)`.

| `rule_id` | `rule` | domain | hard | meaning |
|---|---|---|---|---|
| `atc.runway_exists` | `runway_exists` | atc | yes | runway name not at this airport |
| `atc.runway_open` | `runway_open` | atc | yes | runway closed |
| `atc.taxiway_clear` | `taxiway_clear` | atc | yes | exit taxiway blocked |
| `atc.wake_separation` | `wake_separation` | atc | yes | too close to another arrival on that runway (ICAO Doc 4444 §5.8.2) |
| `atc.slot_window` | `slot_window` | atc | yes | outside `[earliest_arrival_min, max_arrival_min]` |
| `atc.sector_delay` | `sector_delay` | atc | no | cost = delay minutes |
| `pilot.final_reserve_fuel` | `final_reserve_fuel` | pilot | yes | holding would eat into final reserve (EASA CAT.OP.MPA.181) |
| `pilot.connections` | `connections` | pilot | no | cost = 2 × passengers missing onward flights |
| `ground.gate_exists` | `gate_exists` | ground | yes | gate name not at this airport |
| `ground.gate_available` | `gate_available` | ground | yes | gate not free at arrival time |
| `ground.gate_overrun` | `gate_overrun` | ground | no | turnaround holds the gate past its free window; cost per minute |
| `ground.crew_overtime` | `crew_overtime` | ground | no | cost = 1.5 × overtime minutes |
| `operator.*` | `<name> (operator)` | any | varies | rules captured from operators (semantic/elicitation.yaml), e.g. `operator.pilot.divert_buffer`, `operator.ground.gate_board_buffer`. The set can grow; render them generically and label them "operator knowledge" |

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
