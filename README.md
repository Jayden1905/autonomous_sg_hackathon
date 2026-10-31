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
boundaries. The integrated frontend combines Daniel's airport and Flight components
with Bill's negotiation stream, evidence/rule inspector, history and export.
See [frontend/README.md](frontend/README.md) for setup and the integration boundary.

Run `make serve` in one terminal, then `cd frontend && npm ci && npm run dev`
in another. Open `http://127.0.0.1:5173`. Mock agents are selected by default;
they use the backend rule engine without API credentials. Choose Live AI in
Run settings to use the server's configured model. Daniel's standalone recorded
component preview remains available at `/preview.html` during development.

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

**Limits now come from the organisers' constraints workbook** (`challenge2_operational_constraints.xlsx`, exported to `data/airport_capacity.csv`): wake separation (FAA JO 7110.65, simplified), 30 min final reserve with 45 min spare holding on arrival, and minimum turnaround per destination airport. The evaluation figures below were measured before this switch, and the hand-tuned demo scenarios that depended on the earlier ICAO wake table are marked xfail in the tests.

`scenarios/sample_weather.json` is a hand-written scenario so the system runs
before the dataset is downloaded.

## Evaluation

Two runs over the organisers' dataset (rows with `WEATHER_DELAY > 15` or
`LATE_AIRCRAFT_DELAY > 20`, operator rules on). `uv run atc batch` produces the
traces; `uv run atc impact <traces.jsonl>` compares them with what actually
happened to the same flight.

| | 200 rows, scripted | 20 rows, real agents, first in file | 20 rows, real agents, sampled |
|---|---|---|---|
| Rows drawn from | first 200 (all 1 Jan) | first 20 (all 1 Jan) | 10 months, 20 destinations (`--sample --seed 2026`) |
| Consensus | 194 (97%) | 20 (100%) | 17 (85%) |
| Fallback to solver | 0 | 0 | 0 |
| Declined: no legal option | 6 | 0 | 3 |
| Turns, mean | 2.0 | 1.0 | 1.3 |
| Decision time, mean | 0.3 s | 50 s (max 65 s) | 87 s (max 374 s; the three refusals ran all 3 turns) |
| Vetoed accepts (agent agreed to an illegal plan) | 0 | 0 | 0 |
| Passengers kept on connections | 5,252 of 5,447 (96.4%) | 516 of 582 (88.7%) | 488 of 508 (96.1%) |
| LLM calls / tool calls | — | 168 / 257 | 251 / 359 |
| Citation checks / claims sent back for re-grounding | — | 98 / 38 | 123 / 51 |

The first-20 rows are one day at a few hubs and every negotiation closed in one turn.
The sampled rows are harder: three disruptions (DL1690 ATL–BDL in December, MQ3486
ORD–MQT in August, OO7403 MSP–HIB in January) went the full three turns and ended
with no legal plan, which the system reported rather than inventing one. Agents
converge fast when a legal plan exists because they call `check_proposal` (the rule
engine) before proposing. The 89 rejected claims across both real runs are the
guardrail doing its job: a claim whose citation did not resolve to the semantic
model was returned to the agent instead of being spoken. None reached a proposal.

Reproduce: `uv run atc batch data/flights.csv --n 20 --sample --seed 2026 --out run.jsonl`
then `uv run atc impact run.jsonl`.

### Impact against the recorded 2015 outcome

The baseline is real: each DOT row records the flight's actual `ARRIVAL_DELAY`.
Only post-departure delay is comparable, because a flight cannot arrive before its
recorded departure delay.

| Measure | Status | 200 scripted | 20 real, first in file | 20 real, sampled |
|---|---|---|---|---|
| Decision time per disruption | measured | 0.3 s | 50 s | 87 s |
| vs. today | not quantified | phone/radio coordination across three organisations; no published per-flight figure found | | |
| Passengers kept on connections | measured | 96.4% | 88.7% | 96.1% |
| Plans refused because nothing legal existed | measured | 6 of 200 | 0 of 20 | 3 of 20 |
| Holding absorbed per flight | measured | median 3 min | median 4.5 min | median 4 min |
| Fuel burned in hold | estimate (40 kg/min, A320 planning figure) | median 120 kg | median 180 kg | median 160 kg |
| Post-departure delay vs recorded | measured | **median 3 min worse** (47 better, 119 worse, 28 same) | **median 3 min worse** (6 / 12 / 2) | **median 3 min worse** (1 / 13 / 3) |

**The delay number is against us, and we report it.** In 121 of 194 scripted rows
(62.4%), 13 of 20 first-in-file real rows (65%) and 15 of 17 sampled real rows (88%)
the real system had already absorbed the disruption before arrival: the recorded
post-departure delay is 0. There was nothing left for a negotiation to
remove, and the holding our synthetic runway imposes shows up as "worse". On this
dataset the disruption lives at departure; delay minutes cannot be claimed in our
favour, and the comparison says more about the synthetic congestion than about the
agents. The measures the data can support are speed of coordination, connections
protected, and honest refusals.

### Like-for-like: flights delayed on arrival

Our system resolves a disruption at the destination (runway, sequence, gate). Most rows
record their delay at departure, which no arrival plan can change, so we also evaluated
only rows where the recorded delay grew by at least 15 min after takeoff
(`ARRIVAL_DELAY - DEPARTURE_DELAY >= 15`: 39,141 of 358,774 rows), sampled across months
and destinations the same way.

| Measure | 200 scripted | 20 real agents |
|---|---|---|
| Consensus | 194 (6 declined) | 20 of 20, all in 1 turn |
| Recorded post-departure delay, 2015 | median 26 min | median 34 min |
| Negotiated | median 5.5 min | median 29 min |
| Median per-flight difference | **17 min better** (159 better, 33 worse) | **16 min better** (14 better, 6 worse) |
| Passengers kept on connections | 91.4% | 84.3% |
| Vetoed accepts / guardrail-blocked replies | 0 / — | 0 / 0 |

Indicative, not measured savings: the 2015 baseline is real, our side runs on the
synthetic airport. The real agents' plan cost more than the solver's in 9 of 20 rows
(they waited for a preferred gate); every plan was legal.

### Private moves: where negotiation finds what a solver can't

Each organisation can hold options only it knows (`Scenario.moves`): Ground can tow a
parked aircraft or call a standby crew, Pilot can absorb delay en route, ATC can
re-sequence an arrival or reopen a runway. An agent is briefed on its own moves only;
the rule engine applies a plan's moves and still checks every rule. The solver sees the
shared picture only.

`scenarios/demo_storm_aa1453_moves.json` (real AA1453 CLT-ORD, 8 May 2015; airport
synthetic): no legal plan exists without moves, and no single owner's moves suffice.
5 of 5 real-agent runs reached consensus in 2 turns (83-124 s): ATC offers to
re-sequence a heavy and says the gate needs a ground move; Ground adds a tow. 2 of 5
found the cheapest plan (t+56, cost 94.5), 3 landed a minute later (cost 97). Caveat: a
solver given every party's private options would also find it; in practice those
options are not shared up front. Moves exist only in this hand-built scenario so far.

### Known failure cases

- `scenarios/demo_storm_vx204_divert.json`: minimum fuel plus a saturated runway. No
  plan passes every hard rule; the system returns `no_legal_option` with the failing
  rules listed rather than proposing anything.
- The ATC agent's first proposal on `sample-weather-ORD` missed the gate window; the
  rule engine rejected it and the agents converged on the next turn. The LLM got the
  wake spacing and fuel right and the gate wrong; the code caught it.
- Across the 40 real-agent runs the citation guardrail sent 89 of 221 claims back to
  the agent because their source did not resolve to the semantic model. That is the
  LLM reaching for a number it did not have; the guardrail is what stops it being said.
- Three of the 20 sampled real-agent rows (DL1690, MQ3486, OO7403) negotiated for the
  full three turns and ended with no plan that passed every hard rule. The system
  reported `no_legal_option` with the failing rules. These are dataset rows, not
  hand-written cases: a regional flight into a small airport with the generated
  runway closed and tight fuel has no legal slot, and the right answer is to say so.
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
