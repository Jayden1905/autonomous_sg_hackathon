import { describe, expect, it } from "vitest";
import storm from "../../../scenarios/demo_storm_ua599.json";
import type { FlightView, Scenario } from "@/workspace";
import { planFocus } from "./plan-focus";
import { stormLayout } from "./layout";
import { scenarioFleet, scenarioSlots } from "./fleet";

const idle: [number, number, number] = [-18, 0, 39];
const proposal = {
  arrival_min: 60,
  runway: "27R",
  gate: "B6",
  rationale: "Test",
};
const view: FlightView = {
  scenario: storm as Scenario,
  proposal,
  evaluation: null,
  context: "proposal",
  selection: null,
  onSelect: () => {},
};
const compare = (before: Partial<typeof proposal>) => ({
  ...view,
  comparison: { proposal: { ...proposal, ...before }, label: "Previous" },
});

describe("negotiation camera destinations", () => {
  it("frames the changed gate", () => {
    expect(planFocus(compare({ gate: "C9" }), stormLayout, idle)).toMatchObject(
      {
        target: [13, 0, 39],
        distance: 125,
        label: "Proposal preview · Gate C9 → B6",
      },
    );
  });
  it("frames a runway change independently of the gate", () => {
    expect(
      planFocus(compare({ runway: "27L" }), stormLayout, idle),
    ).toMatchObject({ target: [-55, 0, -218], distance: 230 });
  });
  it("frames the whole final recommendation and removes it on no legal option", () => {
    const evaluation = { proposal, feasible: true, cost: 0, results: [] };
    expect(
      planFocus(
        { ...view, evaluation, context: "consensus" },
        stormLayout,
        idle,
      ).distance,
    ).toBe(420);
    expect(
      planFocus(
        { ...view, evaluation, context: "no_legal_option" },
        stormLayout,
        idle,
      ),
    ).toMatchObject({
      target: idle,
      label: "No legal option · Human decision required",
    });
  });
  it("does not aim at a similarly named resource absent from the scenario", () => {
    expect(
      planFocus(
        { ...view, scenario: { ...view.scenario, gates: [], runways: [] } },
        stormLayout,
        idle,
      ).target,
    ).toEqual(idle);
  });
  it("does not issue a new camera cue for rationale or thinking updates", () => {
    const current = planFocus(view, stormLayout, idle);
    expect(
      planFocus(
        {
          ...view,
          proposal: { ...proposal, rationale: "More explanation" },
          awaitingProposal: true,
        },
        stormLayout,
        idle,
      ).key,
    ).toBe(current.key);
  });
  it("focuses the resource affected by an offered agent move", () => {
    const move = {
      id: "ground.tow",
      owner: "ground" as const,
      label: "Tow the aircraft off C9 early",
      effect: { gate_free_from: { gate: "C9", free_from_min: 40 } },
      cost: 10,
      private: true,
    };
    const next = {
      ...compare({}),
      scenario: { ...view.scenario, moves: [move] },
      proposal: { ...proposal, moves: [move.id] },
    };
    expect(planFocus(next, stormLayout, idle)).toMatchObject({
      target: [75, 0, 39],
      label: `Proposal preview · ${move.label}`,
    });
  });
});

describe("scenario aircraft", () => {
  const scenarios = Array.from({ length: 30 }, (_, i) => ({
    ...view.scenario,
    scenario_id: `case-${i}`,
  }));
  it("gives separate scenarios unique illustrative slots, even for the same flight number", () => {
    const fleet = scenarioFleet(scenarios.slice(0, 6), scenarios[2]);
    expect(new Set(fleet.map((item) => item.position.join(","))).size).toBe(6);
    expect(scenarioFleet(scenarios, scenarios[2])[2].position).toEqual(
      fleet[2].position,
    );
  });
  it("bounds scene cost and always includes the active scenario", () => {
    const fleet = scenarioFleet(scenarios, scenarios[25]);
    expect(fleet).toHaveLength(scenarioSlots.length);
    expect(fleet.some((item) => item.scenario.scenario_id === "case-25")).toBe(
      true,
    );
    expect(new Set(fleet.map((item) => item.position.join(","))).size).toBe(
      fleet.length,
    );
  });
});
