import { describe, it, expect } from "vitest";
import type { FlightView, Scenario } from "@/workspace";
import weather from "../../../scenarios/sample_weather.json";
import { demoLayout, resolveScene, unmappedResources } from "./layout";

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
      proposal: { ...view.proposal!, gate: "UNKNOWN", runway: "09R" },
    };
    expect(resolveScene(next, demoLayout)).toMatchObject({
      gate: undefined,
      runway: undefined,
      missing: ["Gate UNKNOWN", "Runway 09R"],
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
});
