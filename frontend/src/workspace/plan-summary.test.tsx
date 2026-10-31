// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { PlanSummary } from "./plan-summary";

afterEach(cleanup);
const before = {
  arrival_min: 28,
  runway: "27R",
  gate: "B12",
  rationale: "First",
};
it("shows only actual changes and links both resources to inspection", () => {
  const onSelect = vi.fn();
  render(
    <PlanSummary
      title="Proposal preview"
      proposal={{ ...before, arrival_min: 34, gate: "B14" }}
      comparison={{ proposal: before, label: "Compared with turn 1" }}
      onSelect={onSelect}
    />,
  );
  expect(screen.getByText("Compared with turn 1 · 2 changes")).toBeTruthy();
  expect(screen.getByText("6 min later")).toBeTruthy();
  expect(screen.getAllByText("27R")).toHaveLength(1);
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect previous gate B12" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Inspect gate B14" }));
  expect(onSelect.mock.calls).toEqual([
    [{ kind: "gate", id: "B12" }],
    [{ kind: "gate", id: "B14" }],
  ]);
});
it("calls an identical plan unchanged, without fabricating gains", () => {
  render(
    <PlanSummary
      title="Last attempt"
      proposal={before}
      comparison={{ proposal: before, label: "Compared with turn 1" }}
    />,
  );
  expect(screen.getByText(/Plan unchanged/)).toBeTruthy();
  expect(screen.queryByText(/earlier|later/)).toBeNull();
});
