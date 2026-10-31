import { describe, expect, it } from "vitest";
import { displayPlan, relativeMinutes } from "./presentation";
import type { Evaluation, Proposal, ViewContext } from "./types";

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
