# Demo handoff

The demo runs on a laptop. Everything below is verified against `main`.

## Local demo, start to finish

```bash
git clone https://github.com/Jayden1905/autonomous_sg_hackathon.git && cd autonomous_sg_hackathon
cp .env.example .env        # paste ANTHROPIC_API_KEY
make setup                  # ~1 min
make demo-check             # prints ✓ / ✗ per item and the next command
make serve                  # http://localhost:8000, Ctrl-C to stop
```

`make demo-check` is the thing to run first on the demo machine. It verifies uv, deps, the API key, the
semantic model, a mock negotiation, and whether :8000 is free, and names the fix for anything missing.

Dataset: optional. The demo scenarios are self-contained. With the organisers' zip in the repo root,
`make data` enables the agents' SQL tool and `/dot/scenarios`.

Stopping: Ctrl-C in the `make serve` terminal. If a server is already on :8000 from earlier, `make demo-check`
says so; stop that one before starting another, never run two.

## Where to look

| What | URL |
|---|---|
| Health, shows model and whether the dataset is present | `http://localhost:8000/health` |
| API docs (every endpoint, every event schema) | `http://localhost:8000/docs` |
| Semantic model viewer (ontology, rules, sources, operator knowledge, agent briefs) | `http://localhost:8000/semantic/` |
| Elicitation: the questions the documents left open, coverage, answers | `http://localhost:8000/semantic/elicitation` |
| Live negotiation stream for the FE | `POST /negotiate/stream` |

Terminal alternative with no server: `make demo` (real agents, ~1 min) or `make demo-mock` (instant, no key).
Pick the scenario with `make demo DEMO_SCENARIO=scenarios/demo_storm_vx204_divert.json`.

## The four scenarios (`GET /scenarios`)

| id | What it shows | Expected outcome |
|---|---|---|
| `demo-storm-ORD-UA599` | Storm at ORD, one runway closed. Agent routes around the operator's gate buffer (t+55 → t+70) and cites it | consensus, 1 turn, t+70 / 27R / B6 |
| `demo-storm-ORD-VX204-divert` | Same storm, minimum fuel, saturated runway | `no_legal_option`: the system declines and says why |
| `sample-weather-ORD` | The original hand-written case; shows a rule-engine veto if the ATC agent misses the gate window | consensus, 1–2 turns |
| `sample-no-legal-option-ORD` | Hand-written impossible case | `no_legal_option` |

Mock mode (`"mock": true`) runs the same event sequence in under a second with no API key.

## What to say out loud (the honest-evaluation points)

- Hard constraints are 130 lines of Python; the LLM proposes, code decides. Every threshold is sourced to ICAO Doc 4444, EASA CAT.OP.MPA.181 or BTS. `semantic/SOURCES.md` has the URLs.
- Runways, gates, fuel, connections and crew shifts are **synthetic**: the DOT data does not have them. Every scenario lists them in `synthetic_fields`.
- Operator knowledge is a **worked example**, not real interviews. The elicitation stage generated 30 questions from the model's own gaps; a model author wrote the answers to exercise the stage. Every passage and rule from it is labelled "operator knowledge (worked example)". Five priority-1 questions are ready for a real controller, pilot or ramp supervisor: `uv run atc semantic elicit`.
- Wake separation is time-based ICAO minima at 150 kt, not RECAT. Fuel is minutes of endurance, no alternate or contingency. One flight at a time.
- The `no_legal_option` outcome is a feature: the system refuses to invent a plan when none passes every hard rule.

## Numbers (mock agents, 200 DOT rows, operator rules on)

194 consensus (97%), 0 fallback, 6 no legal option, 2.03 turns average, 0 vetoed accepts. Real-agent demo runs: 50–55 s, 1 turn, 14 tool calls, 5 guardrail checks.

## Ownership (one owner per file; others send changes)

- Backend, rule engine, semantic model, contracts: Jayden (this repo's `main`)
- Frontend shell, negotiation panels, history: Bill. 3D airport scene, Flight tab: Daniel. See `design/team-handoff.md`.
