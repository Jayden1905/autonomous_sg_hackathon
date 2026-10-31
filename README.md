# ATC / Pilot / Ground negotiation

Autonomous SG 2026, Airbus Challenge 2: *"How might AI help air traffic
controllers, pilots and ground operations staff make faster and better
decisions?"*

Three AI agents, each owning one domain, negotiate a recovery plan for a
disrupted arrival: a revised arrival slot, runway and gate. They have at most
three turns. Hard operational constraints are enforced by code, not by the
agents. If they fail to agree, a deterministic solver decides.

## Who this is for

An airline duty manager or tower supervisor at a hub during a weather or
late-aircraft disruption. Today the three parties coordinate by phone and
radio, one flight at a time. The cost is aircraft holding on fuel, passengers
missing connections and crews running into overtime while the calls happen.

## How it works

```
             ┌──────────┐   proposal    ┌──────────────┐
  scenario ─▶│ ATC agent│──────────────▶│  rule engine │ hard + soft rules, pure code
             └──────────┘               └──────┬───────┘
                                               │ evaluation
                              ┌────────────────┴───────────────┐
                              ▼                                ▼
                       ┌────────────┐                   ┌─────────────┐
                       │Pilot agent │ accept / counter  │Ground agent │ accept / counter
                       └────────────┘                   └─────────────┘
       cheapest feasible counter becomes the next proposal; max 3 turns
                              │
                     consensus │ or fallback.solve()  (enumerates every slot × runway × gate)
```

- `atc_negotiation/schemas.py`: the message types. Agents only speak
  `Proposal` and `AgentResponse`, enforced by structured outputs.
- `atc_negotiation/rules.py`: the constraints. Hard rules (closed runway,
  taxiway blocked, wake separation, fuel final reserve, gate occupied, slot
  window) make a plan infeasible. Soft rules (sector delay, missed
  connections, crew overtime) only add cost.
- `atc_negotiation/agents.py`: one prompt per role. Each agent sees the rule
  engine's verdict on the proposal before answering. `MockAgent` is a
  scripted stand-in for tests and offline demos.
- `atc_negotiation/orchestrator.py`: the turn loop, convergence check,
  rule-engine veto of accepts on infeasible plans, and the fallback handoff.
- `atc_negotiation/fallback.py`: LLM-free solver. Same input, same answer.
- `atc_negotiation/data.py`: builds scenarios from DOT 2015 `flights.csv`.

### What the LLM does and does not do

| LLM | Code |
|---|---|
| Propose a slot, runway and gate | Decide whether that plan is legal |
| Explain its rationale and objections | Compute wake gaps, fuel margins, gate windows, costs |
| Choose to accept or counter | Veto an accept on an infeasible plan |
| | Pick the fallback when turns run out |

## Running it

```bash
make setup                       # uv venv + deps
make test                        # rule and orchestrator tests, no API calls
make demo-mock                   # scripted agents on the sample scenario
make demo                        # real agents (needs ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN)

# from the DOT dataset (put flights.csv under data/, it is gitignored)
uv run atc from-dot data/flights.csv --row 3 --out trace.json
uv run atc batch data/flights.csv --n 50 --mock --out results.jsonl
```

Model defaults to `claude-opus-5-5`; override with `ATC_MODEL` or `--model`.

## Frontend (React, separate)

The backend exposes a FastAPI server for the UI:

```bash
make serve        # http://localhost:8000, Swagger at /docs
make contracts    # regenerate contracts/openapi.json and contracts/types.ts
```

Everything the frontend needs is in `contracts/`:

- `CONTRACT.md`: endpoints, the SSE event sequence for the live negotiation view, rule names, a minimal client
- `openapi.json`: source of truth
- `types.ts`: generated TypeScript types (`components["schemas"]["NegotiationTrace"]` etc.)

Pass `mock: true` in `POST /negotiate/stream` while building the UI; same events, no LLM calls.

## Data

The brief's dataset is the US DOT 2015 flight delays set, supplied by the
organisers as `Challenge 2 Airbus -*.zip`. Drop the zip in the repo root and
run `make data` to extract it into `data/` (both are gitignored). We take rows
with `WEATHER_DELAY > 15` or `LATE_AIRCRAFT_DELAY > 20`. The DOT data carries the
flight, route, schedule and delay attribution. It does **not** have fuel
state, runway traffic, gates, connections or crew shifts, so those are
generated deterministically from the row (seeded by flight and date) and
every scenario lists them in `synthetic_fields`. Treat the operational numbers
as illustrative; the negotiation mechanics are what is being evaluated.

`scenarios/sample_weather.json` is a hand-written scenario so the system runs
before the dataset is downloaded.

## Evaluation

`uv run atc batch` reports, over N scenarios: consensus rate, average turns,
fallback count and the number of times an agent accepted a plan the rule
engine then vetoed. Results and a known failure case go here once we have
run the real dataset.

## Simplifications

- Wake separation uses a time-based table approximating ICAO Doc 4444
  distance minima at typical approach speeds, not the full RECAT matrix.
- Fuel is modelled as minutes of endurance against a 30 min final reserve.
  No alternate or contingency fuel.
- Gates have a single free window; no towing between gates.
- One flight is negotiated at a time. Knock-on effects on other flights are
  only captured through the sector delay cost.
