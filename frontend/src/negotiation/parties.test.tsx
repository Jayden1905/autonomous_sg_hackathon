// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { Scenario } from "@/workspace";
import { PartyBriefs } from "./parties";
import { NegotiationPanel } from "./panel";
import { emptyRun } from "./state";

afterEach(cleanup);

const scenario = {
  scenario_id: "t",
  flight: "UA1",
  airline: "UA",
  origin: "BOS",
  destination: "ORD",
  scheduled_arrival_hhmm: "17:55",
  disruption: "storm",
  weather_delay_min: 52,
  late_aircraft_delay_min: 0,
  earliest_arrival_min: 52,
  aircraft_category: "M",
  fuel_endurance_min: 62,
  final_reserve_min: 30,
  connections: [
    { passengers: 23, departs_min: 110, min_connect_min: 35 },
    { passengers: 6, departs_min: 160, min_connect_min: 35 },
  ],
  runways: [
    { name: "27L", open: false, taxiway_blocked: false, arrivals: [] },
    {
      name: "27R",
      open: true,
      taxiway_blocked: false,
      arrivals: [
        { time_min: 55, category: "H" },
        { time_min: 60, category: "M" },
      ],
    },
  ],
  gates: [
    { name: "C9", free_from_min: 30, free_until_min: 72 },
    { name: "B6", free_from_min: 58, free_until_min: 200 },
  ],
  crew_shift_ends_min: 120,
  turnaround_min: 45,
  max_arrival_min: 180,
  moves: [
    { id: "ground.tow_a1", label: "Tow the aircraft off A1", owner: "ground" },
  ],
} as unknown as Scenario;

it("shows each party only what it holds, and what it cannot see", () => {
  render(<PartyBriefs scenario={scenario} />);
  expect(screen.getByText(/Three parties, three views/)).toBeInTheDocument();
  // tower column: runway state and queue, not fuel
  expect(screen.getByText(/1 runway open · 27L closed/)).toBeInTheDocument();
  expect(screen.getByText(/2 other arrivals queued, 1 heavy/)).toBeInTheDocument();
  // cockpit column: fuel margin and passengers
  expect(
    screen.getByText("32 min of holding before final reserve"),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/29 connecting passengers, first bank leaves \+110 min/),
  ).toBeInTheDocument();
  // ramp column: gates, crew, and the private option it can offer
  expect(screen.getByText(/2 gates, C9 free from \+30 min/)).toBeInTheDocument();
  expect(screen.getByText("Crew shift ends +120 min")).toBeInTheDocument();
  expect(screen.getByText("Tow the aircraft off A1")).toBeInTheDocument();
  // every column names what it cannot see
  expect(screen.getAllByText("Can't see:")).toHaveLength(3);
});

it("replaces the generic idle text with the party view when a scenario is given", () => {
  render(
    <NegotiationPanel
      state={emptyRun()}
      selected={null}
      onLatest={() => {}}
      scenario={scenario}
    />,
  );
  expect(screen.getByText(/Three parties, three views/)).toBeInTheDocument();
  expect(screen.queryByText("Ready to negotiate")).toBeNull();
});

it("keeps the generic idle text when no scenario is supplied", () => {
  render(
    <NegotiationPanel state={emptyRun()} selected={null} onLatest={() => {}} />,
  );
  expect(screen.getByText("Ready to negotiate")).toBeInTheDocument();
});
