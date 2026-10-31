# Pitch: five parts, one per scored row

Three minutes, three judges, standing at the laptop. Same words from everyone.
Weights in brackets. Have open: `/semantic/`, `/docs`, one finished real run, the hold scenario.

---

## 1. Problem realism [20%] — 30 s

**User:** the airline duty manager at a hub during a storm. Today they hold two phones:
tower on one, ramp on the other, cockpit on the radio. Three organisations, three sets of
constraints, nobody sees all of them. The controller doesn't know the crew shift ends in
20 minutes; the ramp doesn't know the pilot has 15 minutes of fuel to spare.

**Cost:** the aircraft holds while the humans talk, and afterwards nobody can say which rule
was checked or why that gate. The decision is slow and it's unverifiable.

**Our scope:** one flight, one disruption, a revised slot, runway and gate. Not fleet
recovery, not autonomous control: a recommendation the duty manager approves.

> Say: "We built it for the person holding two phones."

## 2. Technical soundness [25%] — 50 s

Show the UA599 run. Three agents, one per organisation, each with its own prompt and tools.

- **LLM proposes, code decides.** 130 lines of Python hold every hard rule: wake separation,
  fuel reserve, gate window, runway state. The agents cannot waive them. An agent that accepts an
  illegal plan is overruled and the veto is logged.
- **Agents check before they speak.** `check_proposal` runs the rule engine on a draft; that's why
  20 of 20 real runs converged in one turn.
- **Deterministic fallback.** No consensus in 3 turns → a solver enumerates every slot × runway × gate
  and picks the cheapest legal one. Nothing legal → `no_legal_option`, with the failing rules listed.
- Real data: 358k DOT rows, DuckDB under the agents' `query_metric` tool.

> Say: "The language model never does arithmetic or legality. It proposes and explains. Code decides."

## 3. Trust and traceability [20%] — 40 s

Open `/semantic/`. Click `atc.wake_separation`.

- Every rule → its parameters → the regulation passage → the URL. ICAO Doc 4444 §5.8.2 for wake,
  EASA CAT.OP.MPA.181 for fuel, BTS for the delay categories.
- Every claim an agent makes carries a citation; a guardrail checks it resolves to the model before
  the message is sent. In 20 real runs: 98 claims checked, **38 sent back**. That's the LLM reaching
  for a number it didn't have, caught before it was spoken.
- The model also asked what the documents couldn't tell it: 30 questions for a real controller,
  pilot and ramp supervisor. The answers in there today are a **labelled worked example**: we haven't
  interviewed anyone yet. Every one says so on the label.
- Human stays in control: the output is a recommendation with its evidence, or a refusal.

> Say: "A controller can read the trace and verify every number. Today's phone call leaves nothing to verify."

## 4. Honest evaluation [20%] — 40 s

Two batches on the organisers' data, operator rules on:

| | 200 rows, scripted | 20 rows, real agents |
|---|---|---|
| consensus | 97% | 100%, all one turn |
| decision time | 0.3 s | 50 s |
| refused (no legal option) | 6 | 0 |
| vetoed illegal accepts | 0 | 0 |
| citation checks / bounced | — | 98 / 38 |

**Where it fails, shown live:** VX204, minimum fuel, saturated runway. The system refuses and lists
why. Also: the ATC agent's first proposal on the sample scenario missed the gate window; the engine
caught it.

**The measurement that went against us:** we compared negotiated arrival with what actually
happened to each flight in 2015. We're **3 minutes worse on median**. Reason: in 62–65% of rows the
real disruption was absorbed at departure, so by arrival there was nothing left to improve, and our
synthetic runway is busier than the real day was. Delay minutes can't be claimed on this dataset,
and the README says so.

> Say: "We report the number that went against us, and why. Here's what the data can and can't show."

## 5. Impact [10%] — 30 s

What's measured: a cross-organisation decision in **50 seconds**, 89–96% of connecting passengers
protected, and a refusal when nothing legal exists.

**Illustration (labelled, not a measurement):** `demo-hold-UA599-decision-time`. The aircraft is
already holding when the runway closes; every minute deciding is a minute holding. Legal slots on
the open runway are t+4, 5, 9 and 13. Decide in under a minute and the aircraft lands at **t+4**,
3 minutes of holding. Spend 10 minutes on the phone and the first three slots are gone: it lands at
**t+13**, 12 minutes of holding, roughly 360 kg more fuel at the A320 planning rate. Connections
survive either way; what the phone chain costs here is fuel and runway slots, not passengers. That's
the gap decision speed closes **when coordination is on the critical path**. We couldn't measure it
on the 2015 data because it records when planes landed, not how long humans took to agree.

**Adoption constraint:** recommendation only; a duty manager approves. Scope is one flight at a time.

> Say: "Faster and checkable, not fewer minutes on this dataset. Here is the one case where speed is the whole story, and here is why we call it an illustration."

---

## Likely questions, one-line answers

- *Who said the operator knowledge?* Nobody yet. Placeholders, labelled. Five priority-one questions ready for anyone with ramp or tower time.
- *What if the agents agree on something illegal?* Rule engine vetoes it and logs the veto. Show `vetoed_accepts` in the trace.
- *Why not fewer delay minutes?* The dataset records landings, not decision time; the real system had finished deciding before arrival in two-thirds of cases.
- *Is wake separation real?* ICAO time-based minima at an assumed 150 kt, not RECAT. Conservative. Listed in SOURCES.md.
- *What's synthetic?* Runways, gates, fuel, connections, crew. Every scenario lists them. The flight, route, schedule and delay attribution are real.

## Order of tabs on the laptop

1. `/semantic/` with `atc.wake_separation` selected
2. A finished real run (UA599), scrolled to the proposal and its citations
3. `/docs` for a judge who wants to poke the API
4. Terminal: `make demo DEMO_SCENARIO=scenarios/demo_hold_ua599_decision_time.json` pre-run; `make demo-mock` for a live one
