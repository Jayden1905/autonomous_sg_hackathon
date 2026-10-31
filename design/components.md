# Components, data, and states

Read [the visual direction](README.md) first. This is a specification, not implemented UI. Use the existing [generated API types](../contracts/types.ts); do not create parallel scenario/proposal schemas.

## Shared primitives

All select fields use the shared `Select` from `@/workspace`: a neutral trigger,
small chevron, white floating list, subtle hover and a blue selected checkmark.
Group resource options into Runways and Gates; show closure as a text annotation,
not a red selection fill or a disabled inspection target. Weather and quality
options may include one short explanation. Keep control widths aligned per panel.

Menus render outside scrolling panels, choose above/below placement to fit the
viewport, and scroll internally when needed. Support arrows, Home/End, type-ahead,
Enter/Space, Escape, Tab and outside-click dismissal. Escape closes the list before
its containing disclosure. Keep focus on the trigger and use 44px touch targets.
Use this primitive for scene settings, resource selection and run settings.

| Primitive | Specification |
| --- | --- |
| Floating panel | White, 10px radius, one fine border and subtle shadow; 20px padding; accessible title and close action |
| Inspector tabs | Flight / Negotiation / History; 13px text, thin blue active underline; no filled tab pills |
| Data row | Muted label left, primary value right; minimum 36px; tabular numbers; long values wrap |
| Section heading | 14px/600; optional small contextual text right; no coloured icon block |
| Status | Short text plus small icon; neutral by default; semantic colour on icon/text only |
| Icon button | Consistent outline icon; visible focus; accessible name; appropriate hit area; tooltip when meaning is not obvious |
| Run control | Charcoal circular play button with visible Run negotiation / Run again label; one primary action |
| Rule disclosure | Rule label, pass/fail icon, Hard/Soft text; expandable backend detail; soft cost shown separately |
| Empty/error state | One useful sentence and an available next action; never represented by a blank canvas alone |

## Workspace shell and scenario picker

The toolbar shows the selected airport/scenario and “Simulation”. Search opens a temporary scenario list. Use `/scenarios` and `/scenarios/{id}` for bundled examples; `/dot/scenarios` supplies dataset cases when `/health.dot_dataset_available` is true.

The current API has no server-side scenario search endpoint. Initial search can filter loaded scenarios locally and must be labelled accordingly. Do not imply a search across the entire dataset. Missing dataset files should leave bundled demos usable.

Scenario changes reset the active run, transient responses, and proposal preview together. Ignore late events from a previous run. Preserve completed traces only if history explicitly identifies their scenario.

## Airport canvas and tooltip

Gate stand footprints and runway surfaces are selectable, with a quiet hover
outline and equivalent keyboard-operable labels. Selection opens resource details
inside the existing Flight inspector: gate windows, runway/taxiway state and
scheduled arrival slots. Provide a Back to flight action and resource selector.
Inspecting a resource never assigns it or changes the backend scenario. Keep closed
and unmapped resources available through the inspector's accessible list.

Proposal summaries show previous → displayed arrival, runway and gate when there
is an earlier recorded proposal. Label the comparison turn. A historical counter
compares with its own turn's proposal; a repeated final plan compares with the
preceding turn. Never infer an initial assignment from narrative text or scenery.
Both old and new resource values open inspection. Current plan footprints are
blue; changed previous resources use muted dashed outlines and a Previous label.
Suppress both plan footprints for `no_legal_option`; manual inspection still works.

Map entities to scenario runway/gate identifiers through a presentation adapter. Selection opens the same inspector used by the scenario list. A compact aircraft tooltip shows flight identity, route, and the selected proposal's arrival/runway/gate if one exists.

Before a proposal exists, show earliest possible arrival and label runway/gate as unassigned. A suggested gate placement is a proposal preview, not proof the aircraft has landed or docked. Keep “Proposal preview” or equivalent visible when showing an uncommitted plan.

The closure marker represents `runways[].open === false`; a blocked taxiway has its own label. Geometry is illustrative, so do not claim an exact blocked taxiway segment absent backend data. A gate window is not a permanent available/occupied flag: show availability for the selected proposal time, or show the window itself.

## Flight tab

Display flight identity and route first, then disruption and constraints. Use plain data rows and a few dividers.

| UI value | Source / meaning |
| --- | --- |
| Flight and airline | `Scenario.flight`, `airline_name` or `airline` |
| Route | `origin`, `destination`; optional airport metadata for labels |
| Earliest arrival | `earliest_arrival_min`, relative to scheduled arrival |
| Holding margin | `fuel_endurance_min - final_reserve_min`; positive value is holding budget; negative value means already below reserve and must be shown as a deficit |
| Connecting passengers | Sum `connections[].passengers`; this is not automatically the number missing connections |
| Runway state | `runways[].open`, `taxiway_blocked`, and scheduled `arrivals` |
| Gate windows | `gates[].free_from_min` and `free_until_min` |
| Crew and turnaround | `crew_shift_ends_min`, `turnaround_min` |
| Data provenance | `synthetic_fields` and `source`; reveal in a compact disclosure |

No aircraft model, registration, squawk, real position, boarding progress, or servicing readiness is currently supplied. Do not reproduce those fields from the external references with invented values. Airport coordinates describe an airport, not the selected aircraft's location.

## Negotiation tab

Order: current/final plan → agent activity → constraints → run/export controls. Use a compact turn indicator. Keep the current proposal's rationale available; it is central to understanding the negotiation.

The three agent rows use neutral icons and names: ATC, Pilot, Ground. Each row expands to reveal objections, counter-proposal, and its evaluation when supplied. These are compact rows, not separate coloured chat cards.

| Backend event | Presentation |
| --- | --- |
| `started` | Reset run-local state, record scenario/model/turn limit; show Running |
| `thinking` | Mark only the named agent as Proposing or Evaluating; small progress indicator |
| `tool_call` | Append an expandable tool record, including query rows, compiled SQL and model references when supplied |
| `guardrail` | Record citation-check attempts; a failed intermediate check may still be repaired |
| `proposal` | Update active plan; label its author Proposed; clear responses from the previous turn |
| `evaluation` | Update hard-rule checks and soft costs from this evaluation |
| `response` | Show Accepted, Countered, or Acceptance vetoed; reveal objections/counter on expansion |
| `turn_complete` | Append immutable turn to history |
| `done` | Render the outcome-specific final state below |
| `error` | Show Run failed and the useful error message; retain attempted steps as incomplete; offer retry |

The proposer does not emit an acceptance response for its own proposal. Show “Proposed” for that role and “Accepted” for the actual accepting responders. The approved mockup's three Accepted labels illustrate layout, not exact protocol semantics.

Do not carry old acceptance states into a new turn. An accept with `vetoed: true` must show the rule-engine veto. A counter response may have no alternative; display “No alternative supplied” rather than inventing one.

A returned proposal/response with `guardrail.passed === false`, or a role listed in
`TurnRecord.guardrail_blocked`, is **Reply blocked**, even when its verdict says
accept. This is distinct from a rule-engine veto. Resolve `[n]` markers only against
that same object's `evidence` list; a counterproposal has its own sources. Flag
`grounded: false` as unverified and low-trust sources explicitly. Render source
URLs only as HTTP(S) links. Source trust is not a confidence percentage.

Keep “Mock agents” and “Live AI” clearly distinguishable. The mock uses scripted decisions and the same rules; it is not evidence of LLM performance. Disable duplicate submissions while a run is active. If a future Stop watching action only disconnects the client, say so; do not claim the backend has cancelled the run.

## Final decision states

| Outcome | Heading and treatment | Plan handling |
| --- | --- | --- |
| `consensus` | Consensus reached; small green check | Show `final` and `final_evaluation` as the agreed recommendation |
| `fallback` | Fallback plan; small amber indicator; show `fallback_reason` | Show solver-selected `final`; do not claim all agents agreed |
| `no_legal_option` | No legal option — human decision required; red icon and explicit text | No recommended plan. Hide recommendation styling and selected-plan scene emphasis. If inspected, label `final` Last attempt and show its failed hard rules |
| Stream/network failure | Run incomplete or Run failed | Do not promote the last proposal to a final decision; retry/export partial history only if explicitly labelled |

These are recommendations, not commands issued to an airport. Avoid “Clearance issued”, “Aircraft dispatched”, or “Diverted” unless a future backend actually supports those actions. A successful run has an export action for the full trace.

## Rules and formatting

Use `Evaluation.feasible`, `cost`, and each rule's `passed`, `hard`, `detail`, and `cost`. The frontend must not independently decide feasibility. Distinguish hard pass/fail from soft costs; a soft rule can pass and still have a cost.

Times are relative minutes: `+28 min`, `0 min`, `−5 min`. Window labels should say “Relative to scheduled arrival”. Do not label these as local clock times. Soft cost is a weighted score, not dollars or fuel saved. Missing data is “Unavailable”, not zero. Do not invent a confidence percentage.

Use the full generated `NegotiationTrace.outcome` union, including `no_legal_option`.
Use stable `rule_id` values for model lookups; rule labels may change. Regenerate
contracts from the API rather than editing generated TypeScript by hand.

## History and comparison

History defaults to a compact collapsed handle. Opening it reveals completed turns, proposers, responses, vetoes, and rule details. The inspector History tab and drawer share the same selected turn; they are two views of one history, not separate logs.

Comparison uses a compact table: proposal/author, arrival, runway, gate, feasibility, soft cost. Compare only actual recorded proposals and counter-evaluations. Highlight the selected row with a faint blue fill and show that proposal in the scene as a preview.

“Back to latest” restores the current/final decision after inspecting an earlier turn. Historical display must not overwrite active run state. Replay is discrete negotiation history; do not animate invented aircraft trajectories.

## Required future review fixtures

When application work begins, review: no selection, loading, backend unavailable, dataset absent, idle scenario, thinking/proposing, feasible counter, infeasible counter, vetoed accept, consensus, fallback, no legal option, interrupted stream, long rule text, missing airport metadata, and narrow viewport. Include keyboard-only access and a renderer-unavailable state. This document does not add runtime tests or fixtures.
