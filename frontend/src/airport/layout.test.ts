import { describe, it, expect } from "vitest";
import type { FlightView, Scenario } from "@/workspace";
import storm from "../../../scenarios/demo_storm_ua599.json";
import divert from "../../../scenarios/demo_storm_vx204_divert.json";
import hold from "../../../scenarios/demo_hold_ua599_decision_time.json";
import weather from "../../../scenarios/sample_weather.json";
import noOption from "../../../scenarios/sample_no_legal_option.json";
import {
  datasetLayout,
  demoLayout,
  resolveScene,
  stormLayout,
  unmappedResources,
} from "./layout";

const view: FlightView = {
  scenario: weather as Scenario,
  proposal: {
    arrival_min: 28,
    runway: "27R",
    gate: "B14",
    rationale: "Preview",
  },
  evaluation: null,
  context: "proposal",
  selection: null,
  onSelect: () => {},
};
describe("illustrative scene adapter", () => {
  it("maps proposal IDs without interpreting feasibility", () => {
    expect(resolveScene(view, demoLayout)).toMatchObject({
      gate: demoLayout.gates.B14,
      runway: demoLayout.runways["27R"],
      missing: [],
    });
  });
  it("does not map unknown names onto another resource", () => {
    const next = {
      ...view,
      proposal: { ...view.proposal!, gate: "UNKNOWN", runway: "99X" },
    };
    expect(resolveScene(next, demoLayout)).toMatchObject({
      gate: undefined,
      runway: undefined,
      missing: ["Gate UNKNOWN", "Runway 99X"],
    });
  });
  it("does not reuse a layout ID absent from the selected scenario", () => {
    expect(
      resolveScene(
        { ...view, scenario: { ...view.scenario, gates: [], runways: [] } },
        demoLayout,
      ),
    ).toMatchObject({ gate: undefined, runway: undefined });
  });
  it("removes plan emphasis on no legal option", () => {
    expect(
      resolveScene({ ...view, context: "no_legal_option" }, demoLayout),
    ).toMatchObject({ gate: undefined, runway: undefined, emphasize: false });
  });
  it("keeps manual entity inspection separate from recommendation emphasis", () => {
    expect(
      resolveScene(
        {
          ...view,
          context: "no_legal_option",
          selection: { kind: "gate", id: "B12" },
        },
        demoLayout,
      ),
    ).toMatchObject({ gate: undefined, selectedAnchor: demoLayout.gates.B12 });
  });
  it("reports unmapped resources for the accessible list", () => {
    expect(
      unmappedResources(
        {
          ...view.scenario,
          gates: [{ name: "Z1", free_from_min: 0, free_until_min: 10 }],
        },
        demoLayout,
      ),
    ).toEqual(["Gate Z1"]);
  });
  it.each([
    ["samples", [weather, noOption], demoLayout],
    ["storm demos", [storm, divert, hold], stormLayout],
  ])("maps every resource of the bundled %s", (_, scenarios, layout) => {
    for (const scenario of scenarios)
      expect(unmappedResources(scenario as Scenario, layout)).toEqual([]);
  });
  it("maps backend-generated dataset names in the dataset layout only", () => {
    const runway = { open: true, taxiway_blocked: false, arrivals: [] };
    const gate = { free_from_min: 0, free_until_min: 10 };
    const dataset: Scenario = {
      ...view.scenario,
      runways: [
        { ...runway, name: "04L" },
        { ...runway, name: "36R" },
      ],
      gates: ["A1", "A4", "B7"].map((name) => ({ ...gate, name })),
    };
    expect(unmappedResources(dataset, datasetLayout)).toEqual([]);
    expect(unmappedResources(dataset, demoLayout)).toEqual([
      "Gate A1",
      "Gate A4",
      "Gate B7",
      "Runway 04L",
      "Runway 36R",
    ]);
  });
});
