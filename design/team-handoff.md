# Bill and Daniel: frontend handoff

Use the [shared design system](README.md) and [component specification](components.md). The frontend is now implemented in `frontend/`; see its README for run instructions and integration details. Daniel's public components are consumed by Bill's shared shell.

## Ownership

| Owner | Responsibility | Boundary |
| --- | --- | --- |
| Bill | Application shell, shared primitives/tokens integration, run state and API stream, Negotiation tab, rule disclosures, final decision, History tab/drawer and export | Owns the shared selected scenario, current run, active proposal/turn, and selection coordination |
| Daniel | Detailed 3D airport and camera controls, scene selection/highlights, selected-aircraft tooltip, scenario picker, Flight tab and provenance disclosure | Consumes the selected scenario/proposal/selection; emits selection intentions; does not independently run negotiations or decide feasibility |
| Jayden | Backend, agent behaviour, rule engine, dataset access, schemas and generated API contracts | Coordinates contract changes with both frontend owners |

Daniel's scene work is a substantive part of the frontend. Prioritise a reusable illustrative terminal, gates, runways, and aircraft with the approved lighting/material quality; then add selection and proposal highlighting. Detailed scenery can be refined without blocking Bill's negotiation panels.

The inspector shell and tabs are shared. Daniel supplies the Flight content; Bill supplies Negotiation and History content. Do not create separate inspectors or global styles for each person's features.

## Data handoff before building

Agree on these concepts using the existing generated types, then formalise the props/store interface during implementation:

| Shared value | Consumer / purpose |
| --- | --- |
| Selected `Scenario` | Both; one source of flight identity, constraints, and runway/gate IDs |
| Selected scene entity | Daniel renders the selection; Bill coordinates inspector state; distinguish flight/runway/gate entities |
| Displayed `Proposal` and `Evaluation`, or no proposal | Daniel highlights its runway/gate; Bill renders plan/rules; evaluation remains authoritative |
| View context | Distinguish scenario, active proposal, final recommendation, and historical attempt; no-legal-option is never a recommendation |
| Run status and trace | Bill owns; Daniel receives only what the scene needs |
| Selection callbacks | Daniel reports scenario/entity selections to the shared owner; scenario changes reset run-local display coherently |

Keep scenario identity with every saved trace. Scene anchors are presentation data, not additions to backend operational facts. Agree on handling unknown runway/gate names before integration.

## Shared files and workflow

- `design/tokens.css` is the canonical visual token file. Bill coordinates shared-token changes with Daniel; avoid separate colour/spacing systems.
- Use the component names and states in `components.md` when discussing work, so “inspector”, “tooltip”, “history drawer”, and “proposal preview” mean the same thing.
- Once app work is authorised, choose one frontend setup together, then separate feature folders for airport/scenarios and negotiation. Only one person changes the project configuration or dependency lockfile at a time.
- Use separate feature branches and PRs. The current Makefile's `make push` pushes HEAD directly to `main`; do not use it to publish a feature branch.
- Keep changes to API payloads with Jayden and regenerate contracts together. Do not hand-edit generated TypeScript types.
- When reviewing a new component, compare its scale, colour, and density against the approved image at the same viewport size.

## First implementation milestone, when requested

1. Shared shell and tokens with the floating inspector proportions.
2. Daniel's illustrative airport and Flight tab driven by a bundled scenario; Bill's negotiation tab driven by the existing mock SSE stream.
3. Connect selected proposals to runway/gate emphasis and the shared tooltip.
4. Verify consensus, fallback, and no-legal-option states together before adding optional tools.

Implementation now lives in `frontend/src/app`, `frontend/src/api`, and
`frontend/src/negotiation` for Bill, consuming Daniel's existing feature exports.
The root entry point connects to the backend; `/preview.html` retains Daniel's
recorded component harness during development. Production run state is never
read from those recordings. Explicit illustrative mappings for the two storm
scenarios live with the shell; unfamiliar dataset scenarios keep their resources
in the Flight list rather than assigning them arbitrary geometry.
