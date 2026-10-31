# Integrated airport workspace

Bill's application shell connects Daniel's airport, Flight tab and scenario picker to Jayden's API. The root URL runs real backend negotiations; it does not load recorded traces. Mock agents are the default and require no API key or dataset.

Start two terminals from the repository root:

```sh
# Terminal 1
make setup                 # first run only
make serve                 # API on http://127.0.0.1:8000

# Terminal 2
cd frontend
npm ci
npm run dev               # workspace on http://127.0.0.1:5173
```

Select a scenario, then **Run negotiation**. The Negotiation tab streams agent replies, source citations, rule checks and tool activity. History compares recorded proposals and counterproposals; selecting one also previews it in the airport. **Back to latest** restores the final/current plan. **Decision history** retains up to 20 completed runs for this browser session. Export JSON to save a trace beyond a reload.

**Run settings** selects Mock agents or Live AI, turn limit and reasoning effort. Live AI requires backend credentials; no credentials belong in the frontend. Missing CSVs leave bundled scenarios usable and historical metric queries unavailable. When the backend has the dataset, the settings disclosure can load additional scenarios in pages of 20. Unknown airport resource IDs stay in the Flight list without fabricated scene anchors.

**Stop watching** and changing scenarios disconnect this browser from the current stream; the backend may continue. Partial runs are never shown as final recommendations. Failed citation reports block returned replies, while intermediate failed checks may be repaired. A rule-engine veto is distinct from a citation block. `no_legal_option` displays the last attempt and a human-decision message, without recommendation highlights.

The Vite development/preview server proxies `/api` to `http://127.0.0.1:8000`. For Jayden's server, set `ATC_API_TARGET` in `frontend/.env.local` (see `.env.example`) and restart Vite. Static hosting needs an equivalent `/api` reverse proxy or a build-time `VITE_API_BASE_URL` pointing at the API. The frontend never calls the model provider directly.

## Bill's modules and checks

- `src/app`: shell, scenario/run ownership, session history, inspector and run settings.
- `src/api`: typed HTTP client and POST SSE reader using generated contracts.
- `src/negotiation`: run reducer, agent replies, scoped evidence, rule/tool disclosures and comparison.
- Daniel's `airport`, `flight`, `scenarios` and `workspace` public entry points remain the integration boundary.

```sh
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium     # browser tests, first run only
npm run test:e2e                     # needs the API and frontend running above
```

The browser tests use mock agents only and cover consensus, fallback, no legal option, gate selection, trace download, historical inspection, scenario-switch isolation, interrupted streams, mobile, WebGL loss and API reconnection. Screenshots go to the system temp directory under `nushack-e2e` (override with `E2E_OUTPUT_DIR`). `PLAYWRIGHT_EXECUTABLE_PATH` can select an existing Chromium installation. Live model calls are not part of automated verification.

The scene's HTML labels use a dedicated stable portal container. Keep it stable: letting the renderer choose a changing DOM target during initialization caused stale label roots and errors when switching between scenarios with different gates.

## Daniel's airport and Flight components

React 19, TypeScript, Vite, React Three Fiber and Drei. Run from this directory:

```sh
npm ci
npm run dev
npm run typecheck
npm run lint
npm test
npm run build
```

Daniel's original component preview remains at `http://127.0.0.1:5173/preview.html` during development. It works without the backend or external model/font/HDRI downloads. The bottom-left **Review states** control loads recorded backend fixtures for consensus, fallback and no legal option. **Load mock result** loads a recording; it does not start a negotiation or issue an airport command.

## Scope and integration with Bill

`src/preview` is Daniel's independent component harness. Bill's `src/app` now owns the production toolbar, inspector shell, tabs, shared state, negotiation stream and history. Each entry point imports its own shell styles; feature components use CSS modules and the existing `design/tokens.css` values.

The frontend setup and interface below are proposed integration defaults, not a claim of agreement with Bill. Coordinate before merging or making concurrent configuration/lockfile changes. The preview can be removed when Bill's shell consumes the exports.

| Public module | Exports / responsibility |
| --- | --- |
| `@/airport` | `AirportScene`, `AirportLayout`, `demoLayout`: renderer, camera controls, illustrative anchor mapping, tooltip and scene selection |
| `@/flight` | `FlightTab`: inspector content only; accepts the shared `FlightView` |
| `@/scenarios` | `ScenarioPicker`: searches only supplied scenarios; emits the selected `Scenario` |
| `@/workspace` | Generated contract aliases, `FlightView`, display semantics, and small reusable controls/data rows |

```tsx
import { AirportScene } from '@/airport';
import { FlightTab } from '@/flight';
import { ScenarioPicker } from '@/scenarios';
import type { FlightView } from '@/workspace';

// Bill supplies these values from one coordinated store.
const view: FlightView = {
  scenario,
  proposal,       // null before a proposal exists
  evaluation,     // matching backend evaluation; never recomputed in the UI
  context,        // scenario | proposal | history | consensus | fallback | no_legal_option
  selection,      // null or { kind: 'flight' | 'runway' | 'gate', id }
  onSelect,       // intention callback; the shell owns the selection
};

<Suspense fallback={<p role="status">Preparing airport…</p>}>
  <AirportScene view={view} layout={layout} inspectorWidth={340} />
</Suspense>
<FlightTab {...view} /> // inside Bill's single inspector
<ScenarioPicker scenarios={loadedScenarios} selectedId={scenario.scenario_id} onSelect={onScenarioSelect} />
```

`AirportScene` fills a positioned parent and loads the renderer lazily; import `Suspense` from React for its loading boundary. The shell loads `design/tokens.css` once. The camera dock is owned by the airport; do not add a duplicate dock. The scene does not automatically move the camera during negotiation. Focus, reset, top-down, 3D and zoom are explicit user actions. Reduced motion disables camera transitions.

On scenario changes, Bill must reset proposal, evaluation, selection and historical view together and ignore late events from the old run. Generated payload shapes are imported from `contracts/types.ts`, including the evaluation's output proposal type. No generated contracts were edited.

## Mapping and decision semantics

`AirportLayout` explicitly maps resource IDs to presentation anchors. `demoLayout` covers the two original bundled ORD scenarios. It does not infer geography from an airport code or assign unfamiliar IDs by array position. Pass an explicit layout for another scenario. Unmapped names remain in the Flight resource list and an on-canvas notice; Focus is disabled for unmapped gate/runway selections.

Before a proposal, the aircraft has a neutral illustrative location, with earliest arrival and unassigned runway/gate text. A proposal preview may emphasize its mapped resources, but does not imply an actual landing or occupied gate. `consensus` and `fallback` receive recommendation styling only with a matching, feasible backend evaluation. `no_legal_option` never receives plan emphasis; an inspected final value is labelled **Last attempt · not a recommendation**, with human-decision text and failed hard rules. Manual resource selection remains possible and separate from plan emphasis.

Gate windows are shown relative to scheduled arrival rather than converted into permanent occupancy states. A negative holding margin is labelled a reserve deficit. Connecting passengers are not labelled missed connections.

## Visual sources and geometry

- Layout, proportions, controls and colours: [`design/assets/approved-workspace.png`](../design/assets/approved-workspace.png), [`design/README.md`](../design/README.md), [`design/components.md`](../design/components.md), [`design/tokens.css`](../design/tokens.css).
- Model composition reference: [A Minimalist Airport Diorama by agung.ihackstuff](https://sketchfab.com/3d-models/a-minimalist-airport-diorama-5aba9366cbf54255bb17b7fef10d1ab1).
- Geometry in this implementation is newly authored procedural geometry. The Sketchfab asset is not downloaded, bundled or represented as a licensed source asset. Its modular terminal/aircraft/jetway composition is the reference. The result is an illustrative web scene, not a photorealistic replica of the approved image or an accurate airport topology.

Terminal bays, glazing, rounded concourse ends, jet bridges, aircraft and service vehicles reuse components and materials. Repeated facade/roof details use instancing. Concrete texture is deterministic and local. The aircraft uses a shaped fuselage, swept wings, engines and landing gear. Scenery aircraft and vehicles are decorative, with no operational identity. The selected aircraft is interactive.

## Verification and fixture provenance

Unit/component tests cover proposal/evaluation matching, consensus/fallback/no-option display semantics, missing resource anchors, reserve deficits, provenance, scenario filtering, cancellation and selection callbacks. `npm run lint` also checks module entry points, dependency direction and import cycles. Browser checks cover the approved desktop viewport, camera controls and responsive inspector/search behaviour.

Regenerate recorded traces from the repository root using the existing backend:

```sh
uv run python frontend/scripts/fixtures.py
cd frontend
npx prettier --write src/preview/traces.ts
```

The generator runs mock agents only. It fixes recording timestamp/duration for reproducibility; proposal/evaluation/outcome data comes from the backend. `traces.ts` is a checked-in preview fixture, not a generated API contract. The preview's Negotiation and History views are read-only recording viewers for testing Daniel's components; production SSE and negotiation UI remain Bill's responsibility.

WebGL failure preserves the Flight resource list and scenario workflow. Below 900px the preview inspector initially stays closed, then opens as a bottom sheet. Scene objects are also reachable through ordinary keyboard-operable buttons in Flight details. The scenario picker supports Escape and returns focus to its trigger.
