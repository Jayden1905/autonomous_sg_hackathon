import type { Scenario } from "@/workspace";
import type { Point } from "./layout";

// Presentation slots only. A scenario is a separate what-if case, not live traffic.
export const scenarioSlots = [
  ...[-80, -49, -18, 13, 44, 75].map((x) => ({
    position: [x, 0, 39] as Point,
    rotation: 0,
  })),
  ...[-18, 44, 75].map((x) => ({
    position: [x, 0, -38] as Point,
    rotation: Math.PI,
  })),
];

export function scenarioFleet(scenarios: Scenario[], active: Scenario) {
  const unique = [
    ...new Map([...scenarios, active].map((s) => [s.scenario_id, s])).values(),
  ];
  const visible = unique.slice(0, scenarioSlots.length);
  if (!visible.some((s) => s.scenario_id === active.scenario_id))
    visible[visible.length - 1] = active;
  return visible.map((scenario, index) => ({
    scenario,
    ...scenarioSlots[index],
  }));
}
