import type { components } from "../../../contracts/types";

export type Scenario = components["schemas"]["Scenario"];
export type Proposal = components["schemas"]["Evaluation"]["proposal"];
export type Evaluation = components["schemas"]["Evaluation"];
export type Trace = components["schemas"]["NegotiationTrace"];
export type Selection = {
  kind: "flight" | "runway" | "gate";
  id: string;
} | null;
export type ViewContext =
  "scenario" | "proposal" | "history" | Trace["outcome"];

/** Bill owns these values; Daniel's components emit intentions only. */
export interface FlightView {
  scenario: Scenario;
  proposal: Proposal | null;
  evaluation: Evaluation | null;
  context: ViewContext;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}
