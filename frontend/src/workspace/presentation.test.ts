import { describe, expect, it } from "vitest";
import storm from "../../../scenarios/demo_storm_ua599.json";
import weather from "../../../scenarios/sample_weather.json";
import {
  disruptionLabel,
  displayPlan,
  provenanceLabel,
  recordedFlight,
  relativeMinutes,
  sameProposal,
} from "./presentation";
import type { Evaluation, Proposal, Scenario, ViewContext } from "./types";

const proposal: Proposal = {
  arrival_min: 28,
  runway: "27R",
  gate: "B14",
  rationale: "Test proposal",
};
const evaluation: Evaluation = {
  proposal,
  results: [],
  feasible: true,
  cost: 0,
};

describe("displayed proposal authority", () => {
  it("requires the same agent moves before reusing an evaluation", () => {
    expect(sameProposal(proposal, { ...proposal, moves: ["ground.tow"] })).toBe(
      false,
    );
    expect(
      sameProposal(
        { ...proposal, moves: ["a", "b"] },
        { ...proposal, moves: ["b", "a"] },
      ),
    ).toBe(true);
    expect(
      displayPlan({
        proposal: { ...proposal, moves: ["ground.tow"] },
        evaluation,
        context: "consensus",
      }).recommended,
    ).toBe(false);
  });
  it.each(["consensus", "fallback"] as ViewContext[])(
    "requires a matching feasible evaluation for %s",
    (context) => {
      expect(displayPlan({ proposal, evaluation, context })).toMatchObject({
        recommended: true,
        emphasize: true,
      });
      expect(
        displayPlan({
          proposal,
          evaluation: { ...evaluation, feasible: false },
          context,
        }),
      ).toMatchObject({ recommended: false, emphasize: false });
      expect(
        displayPlan({ proposal, evaluation: null, context }),
      ).toMatchObject({ recommended: false, emphasize: false });
      expect(
        displayPlan({
          proposal,
          evaluation: { ...evaluation, proposal: { ...proposal, gate: "B12" } },
          context,
        }),
      ).toMatchObject({
        assessment: null,
        recommended: false,
        emphasize: false,
      });
    },
  );
  it("never promotes a last attempt even if the supplied assessment says feasible", () => {
    expect(
      displayPlan({ proposal, evaluation, context: "no_legal_option" }),
    ).toMatchObject({
      recommended: false,
      emphasize: false,
      label: "Last attempt · not a recommendation",
    });
  });
  it.each(["proposal", "history"] as ViewContext[])(
    "can preview %s without claiming a recommendation",
    (context) => {
      expect(
        displayPlan({ proposal, evaluation: null, context }),
      ).toMatchObject({ recommended: false, emphasize: true });
    },
  );
  it("has no assigned plan before a proposal", () => {
    expect(
      displayPlan({ proposal: null, evaluation: null, context: "scenario" }),
    ).toMatchObject({ recommended: false, emphasize: false });
  });
  it.each([
    [28, "+28 min"],
    [0, "0 min"],
    [-5, "−5 min"],
  ])("formats relative minutes %s", (value, formatted) =>
    expect(relativeMinutes(value as number)).toBe(formatted),
  );
});

describe("scenario provenance", () => {
  it("reads the DOT row behind a recorded flight", () => {
    expect(recordedFlight(storm as Scenario)).toEqual({
      date: "8 May 2015",
      arrivalDelayMin: 88,
    });
    expect(provenanceLabel(storm as Scenario)).toBe(
      "US DOT flight · 8 May 2015",
    );
  });
  it("labels a scenario without a source row as a hand-written sample", () => {
    expect(recordedFlight(weather as Scenario)).toBeNull();
    expect(provenanceLabel(weather as Scenario)).toBe(
      "Hand-written sample · not from the dataset",
    );
  });
  it("keeps a missing recorded arrival unavailable rather than zero", () => {
    const scenario = {
      ...storm,
      source: { ...storm.source, ARRIVAL_DELAY: "" },
    } as Scenario;
    expect(recordedFlight(scenario)?.arrivalDelayMin).toBeNull();
  });
  it.each([
    [52, 0, "Weather disruption"],
    [0, 92, "Late-aircraft disruption"],
    [20, 31, "Weather and late-aircraft disruption"],
    [0, 0, "Disruption"],
  ])(
    "names logged causes (weather %s, late aircraft %s)",
    (weatherDelay, lateAircraftDelay, label) =>
      expect(
        disruptionLabel({
          ...(storm as Scenario),
          weather_delay_min: weatherDelay,
          late_aircraft_delay_min: lateAircraftDelay,
        }),
      ).toBe(label),
  );
});
