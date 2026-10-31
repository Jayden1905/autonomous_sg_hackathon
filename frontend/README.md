# Integrated airport workspace

All dropdown fields use `workspace/Select`, including weather, quality, resources,
agent mode, turn limit and reasoning effort. It provides a portal listbox with
viewport-aware placement, grouped options, keyboard/type-ahead interaction and
touch targets. No extra UI library is required. Run `npm run test:dropdowns` for
desktop/touch selection, keyboard dismissal, resource focus and menu bounds.

### Resource inspection and plan changes

Click a gate's stand footprint or a runway surface (or focus its label and press
Enter) to inspect it in the existing Flight panel. The panel shows scenario gate
windows, runway/taxiway state and scheduled arrival slots. Back to flight returns
to the flight overview. The resource selector also works for unmapped resources;
inspection does not assign them to the flight.

Flight and Negotiation summaries compare actual recorded proposals. Changed
values show previous → displayed, with a relative arrival delta and the comparison
turn. Both resource values are clickable. Scene labels distinguish Plan and
Previous; previous resource footprints are muted and dashed. No-legal-option
outcomes suppress plan emphasis, while manual resource inspection remains available.

Apron, roof, asphalt and verge materials use TSL `MeshStandardNodeMaterial` with
the installed r187 `WebGLNodesHandler`, keeping the existing WebGL renderer and
GLSL rain. Shared photographic concrete maps supply colour, normal and roughness
detail; world-space slab joints and dampness add scale. Roof seams, metal/glass
environment reflections, runway wear and muted verge variation keep the scene
close to the approved material direction. Small rooftop louvres and ducts join
the existing static batches. No screen-space reflection or continuous AO pass.

Five locally hosted 1K maps total about 3.3 MiB; see
[asset provenance and CC0 licence](public/materials/README.md). The daylight HDR
is used for environment lighting, not as a background. Aircraft contact shadows
are baked in three offscreen passes only when layout, selected-aircraft position
or quality changes, then reused as one plane. Targets are 256px in Eco and 512px
in High. Moving traffic never leaves baked silhouettes behind. Materials have
no animation/time uniforms; weather only updates the apron moisture uniform.
The compatibility handler adds about 90 kB gzip to the lazy scene bundle; it
does not enter the initial application bundle. No renderer or dependency upgrade.
See the [Three.js compatibility API](https://threejs.org/docs/pages/WebGLRenderer.html#WebGLRenderer.setNodesHandler).

`npm run test:interactions` checks actual mesh clicks, keyboard labels, resource
details, recorded comparisons, no-option emphasis and mobile layout against Vite
and the API. Negotiation transitions in this suite use an explicit UI fixture;
`npm run test:e2e` separately verifies the real backend with mock agents.

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

### Animated airport

The **Scene** control below the airport caption changes weather, pauses motion and
selects Auto/Eco/High quality. The default weather is a visual preset inferred from
the disruption text. Decorative traffic follows taxi/departure/arrival paths and
an airborne circuit; it has no backend flight identity. A selected flight remains
a proposal preview. Closed, blocked and unmapped runways are excluded from the
decorative runway loop. Weather overrides do not modify scenario constraints.

The renderer uses:

- Four shared material/geometry meshes per aircraft, retaining the original shapes.
- Terminal and jet-bridge geometry baked into static material batches at mount,
  including their existing instanced details. The original components remain editable.
- A single GPU-driven line batch for rain (700 drops in Eco, 2,200 in High).
- Photographic apron detail with TSL dampness; no separate puddle meshes.
- One cached contact-shadow plane beneath parked aircraft; no per-frame AO pass.
- Cached static shadow maps, refreshed when the displayed aircraft/layout changes.
  Decorative moving aircraft do not cast expensive dynamic shadows.
- Demand rendering with background updates capped at 24 fps in Eco or 30 fps in
  High. Camera interaction can request extra frames. Auto starts in Eco on narrow
  screens and falls back after sustained low rendering throughput.
- No per-frame React state updates. Reduced motion and hidden tabs stop ambient
  updates; pausing leaves camera/selection controls usable.

These are rendering budgets, not guaranteed FPS on every GPU. Dev-only canvas data
attributes expose sampled FPS, draw calls and scene time for the browser checks.
The material-upgrade desktop storm check measured 190 draw calls (188 in Eco rain),
versus 737 in the initial animated version (about 74% fewer). The paused and
hidden-tab checks both recorded zero additional idle draws. That is a draw-call comparison,
not a hardware FPS promise; the automated browser uses software WebGL.

Run `npm run test:motion` with the API and Vite servers running. It checks moving
scene time, presets, quality, reduced motion, mobile and zero idle draw calls after
pause/visibility changes. `npm run test:e2e` still checks the negotiation workflow.

Implementation references: [R3F demand rendering](https://r3f.docs.pmnd.rs/advanced/scaling-performance),
[R3F frame-loop guidance](https://r3f.docs.pmnd.rs/advanced/pitfalls),
[Three.js ShaderMaterial](https://threejs.org/docs/pages/ShaderMaterial.html),
and [Three.js instancing](https://threejs.org/docs/pages/InstancedMesh.html).

### Application modules

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

Daniel's original component preview remains at `http://127.0.0.1:5173/preview.html` during development. It works without the backend or external model/font/HDRI downloads, using the bundled `scenarios/*.json`. The bottom-left **Review states** control loads recorded backend fixtures for consensus, fallback and no legal option. **Load mock result** loads a recording; it does not start a negotiation or issue an airport command. Recordings exist for the hand-written samples only, so the button is disabled for other flights.

## Scope and integration with Bill

`src/preview` is Daniel's independent component harness. Bill's `src/app` now owns the production toolbar, inspector shell, tabs, shared state, negotiation stream and history. Each entry point imports its own shell styles; feature components use CSS modules and the existing `design/tokens.css` values.

The frontend setup and interface below are proposed integration defaults, not a claim of agreement with Bill. Coordinate before merging or making concurrent configuration/lockfile changes. The preview can be removed when Bill's shell consumes the exports.

| Public module | Exports / responsibility |
| --- | --- |
| `@/airport` | `AirportScene`, `AirportLayout`, `demoLayout`, `stormLayout`, `datasetLayout`: renderer, camera controls, illustrative anchor mapping, tooltip and scene selection |
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

`AirportLayout` explicitly maps resource IDs to presentation anchors. `demoLayout` covers the hand-written ORD samples and `stormLayout` the bundled UA599/VX204 demos. `datasetLayout` covers the runway pairs and gates A1/A4/B7 that the backend generates for `/dot/scenarios`; those names are synthetic, not the real airport's, and the app applies this layout only to scenarios it loaded from that endpoint. No layout infers geography from an airport code or assigns unfamiliar IDs by array position. Pass an explicit layout for another scenario. Unmapped names remain in the Flight resource list and an on-canvas notice; Focus is disabled for unmapped gate/runway selections.

Every scenario is labelled by provenance: a **US DOT flight** with its date when `source` holds the DOT row, otherwise a **hand-written sample · not from the dataset**. The Flight tab shows the DOT record (date, scheduled arrival in local time, actual arrival, delay causes) and marks each value listed in `synthetic_fields` as **Synthetic**. The disruption label names every delay cause the scenario logs rather than assuming weather.

Before a proposal, the aircraft has a neutral illustrative location, with earliest arrival and unassigned runway/gate text. A proposal preview may emphasize its mapped resources, but does not imply an actual landing or occupied gate. `consensus` and `fallback` receive recommendation styling only with a matching, feasible backend evaluation. `no_legal_option` never receives plan emphasis; an inspected final value is labelled **Last attempt · not a recommendation**, with human-decision text and failed hard rules. Manual resource selection remains possible and separate from plan emphasis.

Gate windows are shown relative to scheduled arrival rather than converted into permanent occupancy states. A negative holding margin is labelled a reserve deficit. Connecting passengers are not labelled missed connections.

## Visual sources and geometry

- Layout, proportions, controls and colours: [`design/assets/approved-workspace.png`](../design/assets/approved-workspace.png), [`design/README.md`](../design/README.md), [`design/components.md`](../design/components.md), [`design/tokens.css`](../design/tokens.css).
- Model composition reference: [A Minimalist Airport Diorama by agung.ihackstuff](https://sketchfab.com/3d-models/a-minimalist-airport-diorama-5aba9366cbf54255bb17b7fef10d1ab1).
- Geometry in this implementation is newly authored procedural geometry. The Sketchfab asset is not downloaded, bundled or represented as a licensed source asset. Its modular terminal/aircraft/jetway composition is the reference. The result is an illustrative web scene, not a photorealistic replica of the approved image or an accurate airport topology.

Terminal bays, glazing, rounded concourse ends, jet bridges, aircraft and service vehicles reuse components and materials. Repeated facade/roof details use instancing. Concrete uses shared local photographic maps with procedural world-space joints and wetness. The aircraft uses a shaped fuselage, swept wings, engines and landing gear. Scenery aircraft and vehicles are decorative, with no operational identity. The selected aircraft is interactive.

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
