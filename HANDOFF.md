# Demo handoff

State as pushed on 31 Oct 2026. Everything below is verified against commit `e40744b` on `main`.

## Start / stop (on the VM)

```bash
make setup                                                  # once per clone
make data                                                   # needs the organisers' zip in the repo root
uv run uvicorn atc_negotiation.api:app --host 0.0.0.0 --port 8000 --reload --reload-include '*.yaml'
cloudflared tunnel --url http://localhost:8000 --no-autoupdate      # optional public URL, random, dies with the process
```

`--host 0.0.0.0` so Tailscale can reach it (`make serve` binds loopback only). `--reload --reload-include '*.yaml'`
means a `git pull`, or an edit to `semantic/*.yaml`, is picked up without a restart. Log: `/tmp/atc_serve.log`
(append with `>>`; a `>` redirect from a second command truncates the running server's log).

### Restarting, and the one trap

Under `--reload` the parent `uv run uvicorn …` process holds the port and a child worker answers requests.

- Code or YAML changed: nothing to do, it reloads. For anything else, `touch atc_negotiation/semantic/__init__.py`.
- **Never `kill` the worker pid.** The parent keeps the port but does not respawn, so every request hangs with no
  response (connection accepted, nothing answers). If that has happened, `touch` a watched file to respawn.
- Full stop: kill the parent (`pgrep -af 'uvicorn atc_negotiation'`, the `uv run …` line), wait until
  `ss -ltnp | grep :8000` is empty, then start again. Never start a second copy while one is listening.

## Where to look

| What | URL |
|---|---|
| Health, shows model and whether the dataset is present | `/health` |
| API docs (every endpoint, every event schema) | `/docs` |
| Semantic model viewer (ontology, rules, sources, operator knowledge, agent briefs) | `/semantic/` |
| Elicitation: the questions the documents left open, coverage, answers | `/semantic/elicitation` |
| Live negotiation stream for the FE | `POST /negotiate/stream` |

Tailnet: `http://100.97.150.86:8000`. Public tunnel URL: whatever `cloudflared` prints; it changes every run.

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
