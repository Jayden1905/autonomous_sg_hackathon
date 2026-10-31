// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { FlightView, Scenario } from "@/workspace";
import storm from "../../../scenarios/demo_storm_ua599.json";
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
  it("opens focused gate details with an explicit return to the flight", () => {
    const onSelect = vi.fn();
    render(
      <FlightTab
        {...view}
        selection={{ kind: "gate", id: "B12" }}
        onSelect={onSelect}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Gate B12" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Free from")).toBeInTheDocument();
    expect(screen.queryByText("Flight constraints")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back to flight" }));
    expect(onSelect).toHaveBeenCalledWith({
      kind: "flight",
      id: view.scenario.flight,
    });
  });
  it("shows a runway closure even when its taxiway is not blocked", () => {
    render(<FlightTab {...view} selection={{ kind: "runway", id: "27L" }} />);
    expect(
      screen.getByRole("heading", { name: "Runway 27L" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Closed", { selector: "dd" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Scheduled arrivals" }),
    ).toBeInTheDocument();
  });
  it("shows sourced constraints and connection totals without inventing telemetry", () => {
    // Constraints are other parties' private data until a run has finished.
    render(<FlightTab {...view} context="consensus" />);
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
        context="consensus"
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
  it("hides the recorded outcome until a run has finished, then shows it beside the plan", () => {
    const { unmount } = render(
      <FlightTab {...view} scenario={storm as Scenario} />,
    );
    const row = (label: string) => screen.getByText(label).closest("div")!;
    expect(row("Actual arrival")).toHaveTextContent("Revealed after the run");
    expect(row("Actual arrival")).not.toHaveTextContent("+88 min");
    unmount();
    render(
      <FlightTab
        {...view}
        scenario={storm as Scenario}
        context="consensus"
        proposal={{ arrival_min: 70, runway: "27R", gate: "B6", rationale: "" }}
      />,
    );
    expect(row("What actually happened")).toHaveTextContent("+88 min");
    expect(row("What actually happened")).toHaveTextContent("negotiated +70 min");
  });
  it("keeps other parties' constraints and gate windows private until a run has finished", () => {
    render(<FlightTab {...view} scenario={storm as Scenario} />);
    // Shared facts are visible; the cockpit's and ramp's private limits are not.
    expect(screen.getByText("Earliest arrival")).toBeInTheDocument();
    expect(screen.queryByText("Holding budget")).toBeNull();
    expect(screen.queryByText("Connecting passengers")).toBeNull();
    expect(screen.queryByText("Crew shift ends")).toBeNull();
    expect(
      screen.getByText(/held by the cockpit and the ramp/),
    ).toBeInTheDocument();
    // Runway state is public; gate windows are the ramp's.
    expect(screen.getAllByText("× Closed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Window held by ramp").length).toBeGreaterThan(0);
    expect(screen.queryByText(/→/)).toBeNull();
  });
  it("separates a DOT flight's recorded facts from its synthetic values once the run is done", () => {
    render(
      <FlightTab
        {...view}
        scenario={storm as Scenario}
        context="consensus"
        proposal={{ arrival_min: 70, runway: "27R", gate: "B6", rationale: "" }}
      />,
    );
    const row = (label: string) => screen.getByText(label).closest("div")!;
    expect(screen.getByText("US DOT flight · 8 May 2015")).toBeInTheDocument();
    expect(row("Scheduled arrival")).toHaveTextContent("17:55 local");
    expect(row("Holding budget")).toHaveTextContent("Synthetic");
    expect(row("Connecting passengers")).toHaveTextContent("Synthetic");
    expect(row("Earliest arrival")).not.toHaveTextContent("Synthetic");
    expect(screen.getAllByText(/→/).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Runways and gates are synthetic/),
    ).toBeInTheDocument();
    expect(
      screen.getByTitle("Gen. Edward Lawrence Logan International Airport"),
    ).toHaveTextContent("BOS");
  });
  it("labels a hand-written sample once instead of marking every value", () => {
    render(<FlightTab {...view} />);
    expect(
      screen.getByText("Hand-written sample · not from the dataset"),
    ).toBeInTheDocument();
    expect(screen.queryByText("DOT flight record")).not.toBeInTheDocument();
    expect(screen.queryByText("Synthetic")).not.toBeInTheDocument();
  });
});
