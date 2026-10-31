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

## Running it (local demo, three commands)

Needs `git` and [`uv`](https://docs.astral.sh/uv/getting-started/installation/). Python is fetched by uv.

```bash
cp .env.example .env    # set ANTHROPIC_API_KEY (only needed for real agents)
make setup              # venv + deps, ~1 min
make demo-check         # preflight: tells you exactly what is missing, if anything
make serve              # API on http://localhost:8000
```

Then open:

| | |
|---|---|
| `http://localhost:8000/semantic/` | the semantic model: ontology, rules with sources, operator knowledge, each agent's brief |
| `http://localhost:8000/docs` | every endpoint; try `POST /negotiate/stream` with a scenario from `GET /scenarios` |

Terminal demos, no server needed:

```bash
make demo-mock          # scripted agents, no API key, under a second
make demo               # real agents on the UA599 storm scenario, ~1 min
make demo DEMO_SCENARIO=scenarios/demo_storm_vx204_divert.json   # the "no legal option" case
make test               # 87 tests, no API calls
```

The organisers' dataset is optional for the demo scenarios. To enable the SQL tool and
`/dot/scenarios`, put the Challenge 2 zip in the repo root and run `make data`.
Model defaults to `claude-opus-5-5`; override with `ATC_MODEL` in `.env`.

## Frontend (React, separate)

Bill and Daniel share an approved [design system](design/README.md): a detailed
3D airport workspace with a slim toolbar and one floating white inspector.
It includes the approved mockup, shared tokens, component states, and ownership
boundaries. Read it before starting frontend work. The design system is a
specification; the frontend application is not built yet.

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

## Semantic model (what grounds the agents)

Every number an agent is told, and every number `rules.py` enforces, lives in
one place: `semantic/model.yaml` (curated) plus `semantic/schema.yaml` (profiled
from the CSVs, never hand-edited). Concepts, entity types bound to columns or
flagged synthetic, metrics with formulas, typed rules with parameters, code sets
(BTS delay causes, ICAO wake categories), and quoted passages from the Challenge
2 brief and the regulations (ICAO Doc 4444, EASA CAT.OP.MPA.181, BTS 14 CFR
234.4). Sources and honest limits: `semantic/SOURCES.md`.

- Each agent's system prompt gets `brief_for(role)`: its concepts, metrics,
  HARD/SOFT/PROTOCOL rules with `[passage-id]` citations, the quoted passages,
  and the list of synthetic fields. Deterministic, so it caches.
- Agents can call `lookup(term)` (the `lookup_concept` tool); it returns
  "not in the semantic model" rather than let the LLM guess.
- Every `RuleResult` cites its `rule_id`, so a trace line links back to the
  rule, its parameters and its source.

```bash
make semantic                 # re-profile data/*.csv, validate cross-references
uv run atc semantic brief atc # what the ATC agent is told
uv run atc semantic lookup FRF
make serve                    # then open http://localhost:8000/semantic/
```

The live viewer at `/semantic/` draws the model as a graph (colour = layer,
shape = kind, dashed = synthetic), with a details panel showing definitions,
parameters, quoted sources and neighbours, and tabs for each agent's brief.
JSON for your own rendering: `GET /semantic/graph`.

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

Two runs over the organisers' dataset (rows with `WEATHER_DELAY > 15` or
`LATE_AIRCRAFT_DELAY > 20`, operator rules on). `uv run atc batch` produces the
traces; `uv run atc impact <traces.jsonl>` compares them with what actually
happened to the same flight.

| | 200 rows, scripted agents | 20 rows, real agents (`claude-opus-5-5`) |
|---|---|---|
| Consensus | 194 (97%) | *(running; filled in when the batch lands)* |
| Fallback to solver | 0 | |
| Declined: no legal option | 6 | |
| Turns, mean | 2.0 | |
| Decision time, mean | 0.3 s | ~55 s |
| Vetoed accepts (agent agreed to an illegal plan) | 0 | |
| Passengers kept on connections | 5,260 of 5,447 (96.6%) | |

### Impact against the recorded 2015 outcome

The baseline is real: each DOT row records the flight's actual `ARRIVAL_DELAY`.
Only post-departure delay is comparable, because a flight cannot arrive before its
recorded departure delay.

| Measure | Status | 200-row result |
|---|---|---|
| Decision time per disruption | measured | 0.3 s scripted, ~55 s real, vs phone/radio coordination across three organisations (not quantified; no published per-flight figure) |
| Passengers kept on connections | measured | 96.6% |
| Plans refused because nothing legal existed | measured | 6 of 200 |
| Holding absorbed per flight | measured | median 3 min |
| Fuel burned in hold | estimate | median 120 kg/flight at 40 kg/min (A320 planning figure) |
| Post-departure delay vs recorded | measured | **median 3 min worse** (54 better, 116 worse, 24 same) |

**The delay number is against us, and we report it.** In 127 of 194 comparable rows
(65.5%) the real system had already absorbed the disruption before arrival: the
recorded post-departure delay is 0. There was nothing left for a negotiation to
remove, and the holding our synthetic runway imposes shows up as "worse". On this
dataset the disruption lives at departure; delay minutes cannot be claimed in our
favour, and the comparison says more about the synthetic congestion than about the
agents. The measures the data can support are speed of coordination, connections
protected, and honest refusals.

### Known failure cases

- `scenarios/demo_storm_vx204_divert.json`: minimum fuel plus a saturated runway. No
  plan passes every hard rule; the system returns `no_legal_option` with the failing
  rules listed rather than proposing anything.
- The ATC agent's first proposal on `sample-weather-ORD` missed the gate window; the
  rule engine rejected it and the agents converged on the next turn. The LLM got the
  wake spacing and fuel right and the gate wrong; the code caught it.
- Operator knowledge in the model is a labelled worked example, not an interview.
  Coverage of the elicitation stage is red (9 of 31 questions) until a real
  controller, pilot or ramp supervisor answers.

Every scenario lists its synthetic fields. Every rule the engine enforces cites a
source (`semantic/SOURCES.md`). Wake separation is time-based ICAO minima at an
assumed approach speed, fuel is minutes of endurance with no alternate, and the
negotiation handles one flight at a time.

## Simplifications

- Wake separation uses a time-based table approximating ICAO Doc 4444
  distance minima at typical approach speeds, not the full RECAT matrix.
- Fuel is modelled as minutes of endurance against a 30 min final reserve.
  No alternate or contingency fuel.
- Gates have a single free window; no towing between gates.
- One flight is negotiated at a time. Knock-on effects on other flights are
  only captured through the sector delay cost.

## License

MIT, see [LICENSE](LICENSE). Anyone may use, modify and redistribute the code.

The DOT 2015 flight dataset and the organisers' challenge briefs are not part of
this repository and are not covered by this license. Put the organisers' zip in
the repo root and run `make data` to get the dataset.
