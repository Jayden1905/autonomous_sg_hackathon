// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { FlightView, Scenario } from "@/workspace";
import weather from "../../../scenarios/sample_weather.json";
import { FlightTab } from "./flight";

afterEach(cleanup);
const view: FlightView = {
  scenario: weather as Scenario,
  proposal: null,
  evaluation: null,
  context: "scenario",
  selection: null,
  onSelect: () => {},
};
describe("Flight content", () => {
  it("shows sourced constraints and connection totals without inventing telemetry", () => {
    render(<FlightTab {...view} />);
    expect(screen.getByText("25 min")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
    expect(
      screen.getByText("Times relative to scheduled arrival"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/registration|squawk|boarding progress/i),
    ).not.toBeInTheDocument();
  });
  it("shows a negative holding margin as a reserve deficit", () => {
    render(
      <FlightTab
        {...view}
        scenario={{
          ...view.scenario,
          fuel_endurance_min: 20,
          final_reserve_min: 30,
        }}
      />,
    );
    expect(screen.getByText("Fuel reserve deficit")).toBeInTheDocument();
    expect(screen.getByText("10 min")).toBeInTheDocument();
  });
  it("emits selection intentions for unmapped resource IDs", () => {
    const onSelect = vi.fn();
    render(
      <FlightTab
        {...view}
        onSelect={onSelect}
        scenario={{
          ...view.scenario,
          gates: [{ name: "Z99", free_from_min: 0, free_until_min: 10 }],
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Gate Z99/ }));
    expect(onSelect).toHaveBeenCalledWith({ kind: "gate", id: "Z99" });
  });
  it("renders no-legal-option as a last attempt with failed backend rules", () => {
    const proposal = {
      arrival_min: 22,
      runway: "27L",
      gate: "B12",
      rationale: "Last attempt",
    };
    render(
      <FlightTab
        {...view}
        context="no_legal_option"
        proposal={proposal}
        evaluation={{
          proposal,
          feasible: false,
          cost: 22,
          results: [
            {
              rule: "runway_open",
              domain: "atc",
              passed: false,
              hard: true,
              detail: "Runway 27L is closed.",
              cost: 0,
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByText("Last attempt · not a recommendation"),
    ).toBeInTheDocument();
    expect(screen.getByText("Runway 27L is closed.")).toBeInTheDocument();
    expect(screen.queryByText("Recommended arrival")).not.toBeInTheDocument();
  });
  it("discloses synthetic fields and distinguishes layout from scenario data", () => {
    render(<FlightTab {...view} />);
    fireEvent.click(screen.getByText("Data & provenance"));
    expect(
      screen.getByText("everything: hand-written demo scenario"),
    ).toBeVisible();
    expect(screen.getByText(/Geometry, aircraft placement/)).toBeVisible();
  });
});
