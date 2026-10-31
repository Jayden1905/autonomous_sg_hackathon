import type { FlightView, Proposal, ViewContext } from "./types";

export function relativeMinutes(value: number): string {
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value)} min`;
}

const contextLabels: Record<ViewContext, string> = {
  scenario: "Scenario view",
  proposal: "Proposal preview",
  history: "Historical attempt",
  consensus: "Consensus reached",
  fallback: "Fallback plan",
  no_legal_option: "No legal option — human decision required",
};

export function contextLabel(context: ViewContext): string {
  return contextLabels[context];
}

export function sameProposal(a: Proposal, b: Proposal): boolean {
  return (
    a.arrival_min === b.arrival_min &&
    a.runway === b.runway &&
    a.gate === b.gate
  );
}

/** A mismatched evaluation must never certify the displayed proposal. */
export function displayPlan(
  view: Pick<FlightView, "proposal" | "evaluation" | "context">,
) {
  const { proposal, evaluation, context } = view;
  const assessment =
    proposal && evaluation && sameProposal(proposal, evaluation.proposal)
      ? evaluation
      : null;
  const isFinal = context === "consensus" || context === "fallback";
  const recommended = isFinal && assessment?.feasible === true;
  const emphasize =
    proposal !== null &&
    context !== "no_legal_option" &&
    context !== "scenario" &&
    (!isFinal || recommended);
  return {
    assessment,
    recommended,
    emphasize,
    label:
      context === "no_legal_option"
        ? "Last attempt · not a recommendation"
        : isFinal && !recommended
          ? "Awaiting matching feasible evaluation"
          : contextLabel(context),
  };
}
