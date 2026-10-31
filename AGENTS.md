# Project guidance

For frontend, UI/UX, or visual work, read `design/README.md`,
`design/components.md`, and `design/team-handoff.md` before editing.
Use `design/assets/approved-workspace.png` as the approved visual reference
and `design/tokens.css` as the shared token source for Bill and Daniel.

Preserve the detailed 3D airport, slim toolbar, and one floating white
inspector. Earlier A/B/C dashboard concepts were rejected; do not reintroduce
permanent dashboard columns, oversized status cards, or an always-open
comparison strip by default.

Use the generated API contracts for data shapes. Keep illustrative scene
geometry distinct from backend facts, and handle `no_legal_option` explicitly.
Apply these design rules when implementation is requested; their presence
alone is not a request to build the application.
