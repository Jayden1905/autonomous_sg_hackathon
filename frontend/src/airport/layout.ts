import type { FlightView, Scenario } from "@/workspace";
import { displayPlan } from "@/workspace";

export type Point = [number, number, number];
export interface AirportLayout {
  gates: Record<string, Point>;
  runways: Record<string, Point>;
}

/** Explicit illustrative anchors, not an airport topology or inferred coordinates. */
export const demoLayout: AirportLayout = {
  gates: { B12: [-49, 0, 23], B14: [13, 0, 23], C3: [75, 0, 23] },
  runways: { "27L": [0, 0, -158], "27R": [0, 0, -218] },
};

/** Anchors for the bundled UA599/VX204 storm demos and their illustrations. */
export const stormLayout: AirportLayout = {
  gates: { B6: [13, 0, 23], C9: [75, 0, 23] },
  runways: demoLayout.runways,
};

// The backend invents these names for /dot/scenarios (data.py: _runway_pair and
// the fixed gates), so they say nothing about the real airport.
const datasetHeadings = ["04", "09", "13", "17", "22", "27", "31", "36"];

/** Illustrative anchors for /dot/scenarios; keep separate from demoLayout. */
export const datasetLayout: AirportLayout = {
  gates: { A1: [-49, 0, 23], A4: [13, 0, 23], B7: [75, 0, 23] },
  runways: Object.fromEntries(
    datasetHeadings.flatMap((heading): [string, Point][] => [
      [`${heading}L`, [0, 0, -158]],
      [`${heading}R`, [0, 0, -218]],
    ]),
  ),
};

export function resolveScene(view: FlightView, layout: AirportLayout) {
  const { scenario, proposal, selection } = view;
  const plan = displayPlan(view);
  const gate =
    proposal && scenario.gates.some((g) => g.name === proposal.gate)
      ? layout.gates[proposal.gate]
      : undefined;
  const runway =
    proposal && scenario.runways.some((r) => r.name === proposal.runway)
      ? layout.runways[proposal.runway]
      : undefined;
  const missing = proposal
    ? [
        !gate && `Gate ${proposal.gate}`,
        !runway && `Runway ${proposal.runway}`,
      ].filter((v): v is string => Boolean(v))
    : [];
  const selectedAnchor =
    selection?.kind === "gate" &&
    scenario.gates.some((g) => g.name === selection.id)
      ? layout.gates[selection.id]
      : selection?.kind === "runway" &&
          scenario.runways.some((r) => r.name === selection.id)
        ? layout.runways[selection.id]
        : undefined;
  return {
    ...plan,
    missing,
    gate: plan.emphasize ? gate : undefined,
    runway: plan.emphasize ? runway : undefined,
    aircraft:
      plan.emphasize && gate
        ? ([gate[0], 0, gate[2] + 16] as Point)
        : ([13, 0, 52] as Point),
    selectedAnchor,
  };
}

export function unmappedResources(
  scenario: Scenario,
  layout: AirportLayout,
): string[] {
  return [
    ...scenario.gates
      .filter((g) => !layout.gates[g.name])
      .map((g) => `Gate ${g.name}`),
    ...scenario.runways
      .filter((r) => !layout.runways[r.name])
      .map((r) => `Runway ${r.name}`),
  ];
}
