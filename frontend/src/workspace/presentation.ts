import type { FlightView, Proposal, Scenario, ViewContext } from "./types";

export function relativeMinutes(value: number): string {
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value)} min`;
}

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** The US DOT 2015 row a scenario was built from; null for a hand-written sample. */
export function recordedFlight(scenario: Scenario) {
  const source = scenario.source ?? {};
  const [year, month, day] = [source.YEAR, source.MONTH, source.DAY].map(
    Number,
  );
  if (!year || !month || !day) return null;
  const arrivalDelay = Number.parseInt(String(source.ARRIVAL_DELAY ?? ""), 10);
  return {
    date: dateFormat.format(Date.UTC(year, month - 1, day)),
    arrivalDelayMin: Number.isNaN(arrivalDelay) ? null : arrivalDelay,
  };
}

export function provenanceLabel(scenario: Scenario): string {
  const record = recordedFlight(scenario);
  return record
    ? `US DOT flight · ${record.date}`
    : "Hand-written sample · not from the dataset";
}

/**
 * A DOT row can log both causes, and the backend's narrative picks one by
 * threshold, so name every logged cause instead of re-deriving that choice.
 */
export function disruptionLabel(scenario: Scenario): string {
  const weather = scenario.weather_delay_min > 0;
  const lateAircraft = scenario.late_aircraft_delay_min > 0;
  if (weather && lateAircraft) return "Weather and late-aircraft disruption";
  if (weather) return "Weather disruption";
  if (lateAircraft) return "Late-aircraft disruption";
  return "Disruption";
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
    a.gate === b.gate &&
    JSON.stringify([...(a.moves ?? [])].sort()) ===
      JSON.stringify([...(b.moves ?? [])].sort())
  );
}

/** A mismatched evaluation must never certify the displayed proposal. */
export function displayPlan(
  view: Pick<
    FlightView,
    "proposal" | "evaluation" | "context" | "awaitingProposal"
  >,
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
          : view.awaitingProposal
            ? "Previous proposal · Awaiting next turn"
            : contextLabel(context),
  };
}
