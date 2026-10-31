// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { Trace } from "@/workspace";
import { NegotiationPanel } from "./panel";
import { emptyRun } from "./state";
import type { RunState } from "./state";

afterEach(cleanup);
const proposal = {
  arrival_min: 28,
  runway: "27R",
  gate: "B14",
  rationale: "Arrival plan.",
};
const trace: Trace = {
  scenario_id: "test",
  model: "mock",
  started_at: "2026-10-31T00:00:00Z",
  duration_s: 1,
  outcome: "no_legal_option",
  final: proposal,
  final_evaluation: { proposal, feasible: false, cost: 0, results: [] },
  turns: [],
};
it("labels a no-option final value as an attempt, never a recommendation", () => {
  render(
    <NegotiationPanel
      state={{ ...emptyRun(), status: "done", trace }}
      selected={null}
      onLatest={() => {}}
    />,
  );
  expect(screen.getByText("Last attempt · not a recommendation")).toBeTruthy();
  expect(
    screen.getByText("No legal option — human decision required"),
  ).toBeTruthy();
  expect(screen.queryByText("Agreed recommendation")).toBeNull();
});
it("keeps an infeasible veto and a citation-blocked accept distinct", () => {
  const state: RunState = {
    ...emptyRun(1),
    status: "running",
    turn: 1,
    proposer: "atc",
    proposal,
    responses: {
      pilot: {
        turn: 1,
        agent: "pilot",
        vetoed: true,
        counter_evaluation: null,
        response: { verdict: "accept", summary: "Accepted" },
      },
      ground: {
        turn: 1,
        agent: "ground",
        vetoed: false,
        counter_evaluation: null,
        response: {
          verdict: "accept",
          summary: "Accepted",
          guardrail: { passed: false, checked_claims: 1, attempts: 2 },
        },
      },
    },
  };
  render(
    <NegotiationPanel state={state} selected={null} onLatest={() => {}} />,
  );
  expect(screen.getByText("Acceptance vetoed")).toBeTruthy();
  expect(screen.getByText("Reply blocked")).toBeTruthy();
  expect(screen.getByText("Proposed")).toBeTruthy();
});
it("does not mark a repaired reply as blocked based on an earlier guardrail event", () => {
  const state: RunState = {
    ...emptyRun(1),
    status: "running",
    turn: 1,
    proposer: "atc",
    proposal,
    guards: [
      {
        turn: 1,
        agent: "pilot",
        report: { passed: false, checked_claims: 1, attempts: 1 },
      },
    ],
    responses: {
      pilot: {
        turn: 1,
        agent: "pilot",
        vetoed: false,
        counter_evaluation: null,
        response: {
          verdict: "accept",
          summary: "The revised evidence passes.",
          guardrail: { passed: true, checked_claims: 1, attempts: 2 },
        },
      },
    },
  };
  render(
    <NegotiationPanel state={state} selected={null} onLatest={() => {}} />,
  );
  expect(screen.getByText("Accepted")).toBeTruthy();
  expect(screen.queryByText("Reply blocked")).toBeNull();
});
